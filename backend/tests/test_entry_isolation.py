"""条目空间隔离：法条题卡（kind='card'）不得混进按条目语义查询的结果。

对应 Spec `docs/superpowers/specs/2026-09-20-法条题卡条目化统一-design.md` §3：
- 条目空间（调度、搜索、覆盖树、覆盖率、批量 TTS、出题脚本）读 `v_entries`；
- 卡片可见（看背/听学队列、标记、音频、审阅历史、错题本）直读 `entries`。
"""
import sqlite3

from app import db, generator, service, statute_index, stats

ENTRY_COLS = ("id, subject, submodule, point, anchor, conclusion, priority,"
              " rationale, sources, cases, statutes, note, tts_text, status")


def _entry(conn, entry_id="XF-001", *, subject="刑法", point="正当防卫",
           anchor="情境", conclusion="结论", tts_text="【刑法·正当防卫】文本",
           statutes='["刑法20条"]', status="final"):
    conn.execute(
        f"INSERT INTO entries ({ENTRY_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, subject, "总则-犯罪构成", point, anchor, conclusion,
         "高频考点", "理由", "[]", "[]", statutes, None, tts_text, status),
    )
    conn.commit()
    return entry_id


def _card(conn, entry_id="XF-Q000162", *, subject="刑法",
          point="刑法269条 · 转化型抢劫",
          anchor="甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
          conclusion="成立抢劫罪。",
          tts_text="法条依据：刑法269条。题目：甲的行为如何定性？答案：成立抢劫罪。",
          status="final"):
    conn.execute(
        f"INSERT INTO entries ({ENTRY_COLS}, kind, options, article_text)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'card',"
        "'[\"盗窃罪\",\"抢劫罪\"]','刑法269条原文')",
        (entry_id, subject, "刑法", point, anchor, conclusion,
         "普通", "解析：事后转化。", "[]", "[]", '["刑法269条"]', None,
         tts_text, status),
    )
    conn.commit()
    return entry_id


def test_new_db_has_card_columns_and_view(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    assert {"kind", "options", "article_text"} <= cols
    views = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'").fetchall()}
    assert "v_entries" in views
    _entry(conn)
    _card(conn)
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM v_entries").fetchone()[0] == 1


def test_legacy_db_gets_card_columns_and_view(tmp_db):
    db_path, _ = tmp_db
    raw = sqlite3.connect(db_path)
    raw.executescript(
        "CREATE TABLE entries ("
        " id TEXT PRIMARY KEY, subject TEXT NOT NULL, submodule TEXT NOT NULL,"
        " point TEXT NOT NULL, anchor TEXT NOT NULL, conclusion TEXT NOT NULL,"
        " priority TEXT NOT NULL, rationale TEXT NOT NULL,"
        " sources TEXT NOT NULL DEFAULT '[]', cases TEXT NOT NULL DEFAULT '[]',"
        " statutes TEXT NOT NULL DEFAULT '[]', note TEXT,"
        " tts_text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft')")
    raw.execute(
        f"INSERT INTO entries ({ENTRY_COLS}) VALUES ('XF-001','刑法','总则','正当防卫',"
        "'情境','结论','高频考点','理由','[]','[]','[]',NULL,'文本','final')")
    raw.commit()
    raw.close()

    conn = db.connect(db_path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    assert {"kind", "options", "article_text"} <= cols
    # 旧行默认是正式条目，仍能被 v_entries 看到
    assert conn.execute("SELECT COUNT(*) FROM v_entries").fetchone()[0] == 1


def test_card_excluded_from_entry_space(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _card(conn, point="刑法269条 · 转化型抢劫")

    # 关键词搜索（助手上下文检索）
    assert service._search_entries(conn, "转化型抢劫") == []

    # 覆盖树（今日统计的科目覆盖）
    tree = stats.coverage_payload(conn)
    points = [p for s in tree.values() for sub in s["submodules"].values()
              for p in sub["points"]]
    assert all("269条" not in p for p in points)

    # 法条页「引用了本条的法条条目」反查
    assert statute_index.entries_for(conn, "中华人民共和国刑法", 269) == []

    # 续批生成：卡片不能顶替正式条目的数量
    for i in range(150):
        _card(conn, entry_id=f"MS-Q{i:06d}", subject="民诉", point=f"民诉法{i}条 · 题")
    assert generator.next_pending_subject(conn) == "民诉"


def test_card_visible_to_study_paths(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    card_id = _card(conn)

    assert service.entry_by_id(conn, card_id) is not None
    items, _ = service._listen_pool(conn)
    assert card_id in {i["id"] for i in items}

    # 标记与自评沿用既有表（外键指向 entries）
    conn.execute(
        "INSERT INTO marks (entry_id, created_at) VALUES (?, '2026-09-20T10:00:00')",
        (card_id,))
    conn.execute(
        "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec)"
        " VALUES (?, '2026-09-20T10:00:00', 'read', 'bad', 12)", (card_id,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM marks").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1


def test_update_entry_text_rejects_card(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    card_id = _card(conn)
    entry, err = service.update_entry_text(
        conn, card_id, {"point": "改", "anchor": "改", "conclusion": "改。",
                        "priority": "普通"})
    assert entry is None
    assert "题库同步" in err


def test_ensure_listen_pool_ignores_cards(tmp_db, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _entry(conn)
    for i in range(100):
        _card(conn, entry_id=f"XF-Q{i:06d}", point=f"刑法{i}条 · 题")

    calls = []
    monkeypatch.setattr(generator, "ensure_generation",
                        lambda c: calls.append(1) or True)
    # 正式条目只剩 1 条未听 → 触发续批（卡片不算）
    assert service.ensure_listen_pool(conn, threshold=50) is True
    assert calls == [1]

    calls.clear()
    for i in range(60):
        _entry(conn, entry_id=f"XF-1{i:02d}", point=f"考点{i}")
    assert service.ensure_listen_pool(conn, threshold=50) is False
    assert calls == []
