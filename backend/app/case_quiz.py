"""主观题服务层：选题、下发、作答、按采分点判分。

核心设计：LLM 只负责「压缩案情 + 抽采分点」，**不评判用户写的文字**。
采分点出自案例的裁判理由，可回溯；用户逐条勾「我写到了吗」，据此算分。

题型：`case` 案例分析 / `essay` 论述题 / `composite` 综合大案例。
论述题额外做两项**确定性**形式检查（字数、是否照搬材料），仍不交给 LLM。
"""
import json
from datetime import date, datetime

from app import statutes, subjective_templates as stpl

#: 照搬材料的判定窗口：连续 15 字落在材料原文里即算一个「照搬窗口」
COPY_WINDOW = 15


def _row_payload(row, conn=None) -> dict:
    """题目字典（含答案与采分点，仅供内部与复习用）。"""
    case = None
    if conn is not None:
        c = conn.execute(
            "SELECT title, case_no, category FROM cases WHERE source=? AND loc=?",
            (row["case_source"], row["case_loc"])).fetchone()
        if c is not None:
            case = {"title": c["title"], "case_no": c["case_no"],
                    "category": c["category"]}
    return {
        "id": row["id"], "subject": row["subject"], "stem": row["stem"],
        "questions": json.loads(row["questions"] or "[]"),
        "points": json.loads(row["points"] or "[]"),
        "materials": json.loads(row["materials"] or "[]"),
        "qtype": row["qtype"] or "case",
        "reference": row["reference"], "status": row["status"],
        "case": case,
    }


def public_payload(q: dict) -> dict:
    """对用户下发的部分：题干与设问，**不含参考答案与采分点**。"""
    qtype = q.get("qtype") or "case"
    return {"id": q["id"], "subject": q["subject"], "stem": q["stem"],
            "questions": q["questions"], "case": q.get("case"),
            "qtype": qtype, "materials": q.get("materials") or [],
            "slot": stpl.slot_for(q["subject"], qtype),
            "spec": stpl.spec_for(qtype),
            "skeleton": stpl.skeleton_for(q["subject"], qtype)}


def listen_text(q: dict) -> str:
    """「只听」模式的朗读文本：读材料、题干与设问，**不读答案与采分点**。"""
    parts = [f"【{q['subject']}】"]
    for m in q.get("materials") or []:
        parts.append(f"{m.get('label', '材料')}：{m.get('text', '')}")
    parts.append(q["stem"])
    for i, question in enumerate(q["questions"], 1):
        parts.append(f"第{i}问：{question}")
    parts.append("请在心中作答，想好后回到页面勾选你答到的采分点。")
    return "\n".join(parts)


def pick_daily(conn, day: str | None = None, qtype: str = "case") -> dict | None:
    """今日题：优先没做过的；全做过则取最久未做的。同日重复请求结果稳定。"""
    day = day or date.today().isoformat()
    rows = conn.execute(
        "SELECT * FROM case_questions WHERE status='published' AND qtype=?"
        " ORDER BY id", (qtype,)).fetchall()
    if not rows:
        return None
    last = {r["question_id"]: r["last"] for r in conn.execute(
        "SELECT question_id, MAX(ts) AS last FROM case_attempts GROUP BY question_id")}
    fresh = [r for r in rows if r["id"] not in last]
    if fresh:
        return _row_payload(fresh[date.fromisoformat(day).toordinal() % len(fresh)], conn)
    return _row_payload(min(rows, key=lambda r: last[r["id"]]), conn)


def question_by_id(conn, qid: int) -> dict | None:
    row = conn.execute("SELECT * FROM case_questions WHERE id=?", (qid,)).fetchone()
    return _row_payload(row, conn) if row else None


def submit_answer(conn, qid: int, answer_text: str, duration_sec: int = 0,
                  mode: str = "write") -> dict | None:
    """落一条作答记录并下发采分点核对表（此时才把采分点文本给前端）。"""
    q = question_by_id(conn, qid)
    if q is None:
        return None
    cur = conn.execute(
        "INSERT INTO case_attempts (question_id, ts, mode, answer_text, hit_points,"
        " score, duration_sec) VALUES (?,?,?,?,'[]',0,?)",
        (qid, datetime.now().isoformat(timespec="seconds"), mode,
         answer_text, int(duration_sec)))
    conn.commit()
    return {"attempt_id": cur.lastrowid, "points": q["points"]}


def grade(conn, qid: int, hit_points: list[int]) -> dict | None:
    """提交勾选结果：算分并给出未命中采分点及其法条依据。"""
    q = question_by_id(conn, qid)
    if q is None:
        return None
    points = q["points"]
    total = len(points) or 1
    hit = sorted({int(p) for p in hit_points
                  if isinstance(p, int) or str(p).isdigit()})
    hit = [p for p in hit if 1 <= p <= len(points)]
    score = round(len(hit) / total * 100)
    row = conn.execute(
        "SELECT id, answer_text FROM case_attempts WHERE question_id=?"
        " ORDER BY id DESC LIMIT 1", (qid,)).fetchone()
    if row is not None:
        conn.execute("UPDATE case_attempts SET hit_points=?, score=? WHERE id=?",
                     (json.dumps(hit), score, row["id"]))
        conn.commit()
    missed = [{"no": p["no"], "text": p["text"],
               "kind": p.get("kind", ""),
               "qno": p.get("qno", 0),
               "statutes": p.get("statutes") or [],
               "links": [link for link in (statute_link(s)
                                           for s in (p.get("statutes") or []))
                         if link]}
              for p in points if p["no"] not in hit]
    return {"score": score, "hit": hit, "total": len(points),
            "missed": missed, "reference": q["reference"],
            "by_kind": kind_breakdown(points, hit),
            "essay": essay_metrics(row["answer_text"], q["materials"])
            if q["qtype"] == "essay" and row is not None else None}


def essay_metrics(answer_text: str, materials: list[dict] | None) -> dict:
    """论述题的确定性形式检查：字数是否达标、是否大段照搬材料。

    评分仍由用户勾采分点完成；这里只判「形式红线」——真实评卷里
    「无观点或论述、照搬材料原文的不得分」，字数不达标同样先扣分。
    """
    spec = stpl.SPECS["essay"]
    body = stpl.squash(answer_text)
    chars = len(body)
    source = stpl.squash("".join(m.get("text", "") for m in (materials or [])))
    windows = max(0, chars - COPY_WINDOW + 1)
    copied = sum(1 for i in range(windows)
                 if body[i:i + COPY_WINDOW] in source) if source else 0
    ratio = round(copied / windows, 3) if windows else 0.0
    verdict = []
    if chars < spec["min_chars"]:
        verdict.append(f"字数不足：{chars}/{spec['min_chars']} 字")
    if ratio > stpl.ESSAY_MAX_COPY_RATIO:
        verdict.append(f"大段照搬材料：{round(ratio * 100)}% 与材料原文重合，"
                       "评卷时这部分的论述不得分")
    return {"chars": chars, "min_chars": spec["min_chars"],
            "advise_chars": spec["advise_chars"], "reach": chars >= spec["min_chars"],
            "copy_ratio": ratio, "copy_limit": stpl.ESSAY_MAX_COPY_RATIO,
            "copied": ratio > stpl.ESSAY_MAX_COPY_RATIO,
            "verdict": verdict}


def kind_breakdown(points: list[dict], hit: list[int]) -> list[dict]:
    """按采分点维度统计命中情况，用于看出「结论对但依据缺」这类失分结构。"""
    order = stpl.kind_order()
    stats: dict[str, dict] = {}
    for p in points:
        k = p.get("kind") or "其他"
        d = stats.setdefault(k, {"kind": k, "hit": 0, "total": 0})
        d["total"] += 1
        if p["no"] in hit:
            d["hit"] += 1
    return sorted(stats.values(), key=lambda d: order.get(d["kind"], 99))


def misses(conn, subject: str | None = None, limit: int = 200,
           qtype: str | None = None) -> list[dict]:
    """复盘池：按采分点文本聚合未命中情况。

    同一个采分点在多题里反复未命中才是真薄弱点，所以按文本聚合而非按题罗列。
    """
    rows = conn.execute(
        "SELECT a.hit_points, a.ts, q.id AS qid, q.subject, q.points "
        "FROM case_attempts a JOIN case_questions q ON q.id=a.question_id "
        "WHERE (? IS NULL OR q.qtype=?) ORDER BY a.ts DESC",
        (qtype, qtype)).fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        points = json.loads(r["points"] or "[]")
        hit = set(json.loads(r["hit_points"] or "[]"))
        for p in points:
            item = agg.setdefault(p["text"], {
                "text": p["text"], "kind": p.get("kind", ""),
                "statutes": p.get("statutes") or [], "subject": r["subject"],
                "asked": 0, "missed": 0, "last_missed": None,
                "question_ids": []})
            item["asked"] += 1
            if p["no"] in hit:
                continue
            item["missed"] += 1
            if item["last_missed"] is None or r["ts"] > item["last_missed"]:
                item["last_missed"] = r["ts"]
            if r["qid"] not in item["question_ids"]:
                item["question_ids"].append(r["qid"])
    items = [v for v in agg.values() if v["missed"]]
    if subject:
        items = [v for v in items if v["subject"] == subject]
    items.sort(key=lambda x: (x["missed"], x["last_missed"] or ""), reverse=True)
    for it in items:
        it["links"] = [link for link in (statute_link(s) for s in it["statutes"])
                       if link]
    return items[:limit]


def statute_link(ref: str) -> dict | None:
    """「公司法第23条」→ 法条页直达参数。

    只有该法**确实在 data/法条库 里**才返回链接，否则前端点进去会撞 404
    （法条库尚未补全期间这种情况很常见）。
    """
    m = statutes._ARTICLE_RE.search(ref or "")
    if not m:
        return None
    law = ref[:m.start()].strip()
    no = statutes._cn2int(m.group("num"))
    if not law or no is None or statutes.resolve_law_file(law) is None:
        return None
    return {"ref": ref, "law": law, "no": no,
            "url": f"/statutes?law={law}&no={no}"}


def history(conn, limit: int = 50, qtype: str | None = None) -> list[dict]:
    """作答历史：题干、模式、命中数、得分、未命中采分点。"""
    rows = conn.execute(
        "SELECT a.*, q.subject, q.stem, q.points, q.reference, q.qtype "
        "FROM case_attempts a JOIN case_questions q ON q.id=a.question_id "
        "WHERE (? IS NULL OR q.qtype=?) "
        "ORDER BY a.ts DESC, a.id DESC LIMIT ?",
        (qtype, qtype, limit)).fetchall()
    out = []
    for r in rows:
        points = json.loads(r["points"] or "[]")
        hit = set(json.loads(r["hit_points"] or "[]"))
        out.append({
            "id": r["id"], "question_id": r["question_id"], "ts": r["ts"],
            "mode": r["mode"], "subject": r["subject"], "qtype": r["qtype"],
            "stem": r["stem"],
            "score": r["score"], "hit": sorted(hit), "total": len(points),
            "answer_text": r["answer_text"] or "",
            "missed": [p["text"] for p in points if p["no"] not in hit],
        })
    return out


def stats_summary(conn, qtype: str | None = None) -> dict:
    """总体：做过的题数、平均分、按科目分布（可按题型只看一类）。"""
    rows = conn.execute(
        "SELECT q.subject, COUNT(*) AS n, AVG(a.score) AS avg "
        "FROM case_attempts a JOIN case_questions q ON q.id=a.question_id "
        "WHERE (? IS NULL OR q.qtype=?) GROUP BY q.subject",
        (qtype, qtype)).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM case_attempts a JOIN case_questions q"
        " ON q.id=a.question_id WHERE (? IS NULL OR q.qtype=?)",
        (qtype, qtype)).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(DISTINCT a.question_id) FROM case_attempts a"
        " JOIN case_questions q ON q.id=a.question_id"
        " WHERE (? IS NULL OR q.qtype=?)", (qtype, qtype)).fetchone()[0]
    published = conn.execute(
        "SELECT COUNT(*) FROM case_questions WHERE status='published'"
        " AND (? IS NULL OR qtype=?)", (qtype, qtype)).fetchone()[0]
    return {
        "attempts": total, "questions_done": done, "published": published,
        "by_subject": [{"subject": r["subject"], "n": r["n"],
                        "avg": round(r["avg"] or 0)} for r in rows],
    }
