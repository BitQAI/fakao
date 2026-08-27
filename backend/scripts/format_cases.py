"""案例库统一格式化：4 个来源 → index.csv + documents/*.jsonl。

用法：
    python scripts/format_cases.py [--data DIR] [--out DIR]

默认输入 data/案例数据，默认输出 data/案例库统一。
输出：
    index.csv                    元数据（提交入库）
    documents/<来源库>.jsonl     全文（.gitignore，可再生成）
幂等：重复运行覆盖输出；单文件解析失败记 stderr 不中断。
"""
import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

CASE_SOURCES = ("人民法院案例库", "司法部案例库", "最高检指导性案例", "最高法指导性案例")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u3000]+")
_HEADING_RE = re.compile(r"^##\s*检例第(\d+)号\s*(.*)$", re.MULTILINE)
_BATCH_RE = re.compile(r"第(\d+)批")

# ---- 关键词推导词典（仅用于关键词为空的记录：标题 + 原文提取）----

# 罪名：命中词 → 关键词
_CRIME_TERMS = [
    ("盗窃", "盗窃罪"), ("诈骗", "诈骗罪"), ("抢劫", "抢劫罪"), ("抢夺", "抢夺罪"),
    ("敲诈勒索", "敲诈勒索罪"), ("故意杀人", "故意杀人罪"), ("故意伤害", "故意伤害罪"),
    ("过失致人死亡", "过失致人死亡罪"), ("强奸", "强奸罪"), ("猥亵", "猥亵罪"),
    ("绑架", "绑架罪"), ("拐卖妇女", "拐卖妇女罪"), ("拐卖儿童", "拐卖儿童罪"),
    ("收买被拐卖", "收买被拐卖的妇女、儿童罪"), ("非法拘禁", "非法拘禁罪"),
    ("侮辱", "侮辱罪"), ("诽谤", "诽谤罪"), ("贪污", "贪污罪"), ("受贿", "受贿罪"),
    ("行贿", "行贿罪"), ("挪用公款", "挪用公款罪"), ("挪用资金", "挪用资金罪"),
    ("职务侵占", "职务侵占罪"), ("私分国有资产", "私分国有资产罪"),
    ("非法经营同类营业", "非法经营同类营业罪"), ("为亲友非法牟利", "为亲友非法牟利罪"),
    ("交通肇事", "交通肇事罪"), ("危险驾驶", "危险驾驶罪"),
    ("以危险方法危害公共安全", "以危险方法危害公共安全罪"),
    ("放火", "放火罪"), ("爆炸", "爆炸罪"), ("投放危险物质", "投放危险物质罪"),
    ("非法吸收公众存款", "非法吸收公众存款罪"), ("集资诈骗", "集资诈骗罪"),
    ("信用卡诈骗", "信用卡诈骗罪"), ("保险诈骗", "保险诈骗罪"),
    ("合同诈骗", "合同诈骗罪"), ("贷款诈骗", "贷款诈骗罪"), ("票据诈骗", "票据诈骗罪"),
    ("逃税", "逃税罪"), ("虚开增值税", "虚开增值税专用发票罪"), ("洗钱", "洗钱罪"),
    ("非法经营", "非法经营罪"), ("组织、领导传销", "组织、领导传销活动罪"),
    ("走私", "走私罪"), ("贩卖毒品", "贩卖毒品罪"), ("运输毒品", "运输毒品罪"),
    ("制造毒品", "制造毒品罪"), ("非法持有毒品", "非法持有毒品罪"),
    ("容留他人吸毒", "容留他人吸毒罪"), ("包庇毒品", "包庇毒品犯罪分子罪"),
    ("组织卖淫", "组织卖淫罪"), ("协助组织卖淫", "协助组织卖淫罪"),
    ("引诱、容留、介绍卖淫", "引诱、容留、介绍卖淫罪"), ("强迫卖淫", "强迫卖淫罪"),
    ("开设赌场", "开设赌场罪"), ("赌博", "赌博罪"), ("寻衅滋事", "寻衅滋事罪"),
    ("聚众斗殴", "聚众斗殴罪"), ("妨害公务", "妨害公务罪"), ("袭警", "袭警罪"),
    ("伪证", "伪证罪"), ("妨害作证", "妨害作证罪"), ("帮助毁灭、伪造证据", "帮助毁灭、伪造证据罪"),
    ("窝藏", "窝藏罪"), ("包庇", "包庇罪"), ("掩饰、隐瞒犯罪所得", "掩饰、隐瞒犯罪所得罪"),
    ("帮助信息网络犯罪活动", "帮助信息网络犯罪活动罪"), ("非法利用信息网络", "非法利用信息网络罪"),
    ("拒不支付劳动报酬", "拒不支付劳动报酬罪"), ("遗弃", "遗弃罪"), ("虐待", "虐待罪"),
    ("重婚", "重婚罪"), ("侵犯著作权", "侵犯著作权罪"),
    ("销售假冒注册商标", "销售假冒注册商标的商品罪"), ("假冒注册商标", "假冒注册商标罪"),
    ("侵犯商业秘密", "侵犯商业秘密罪"), ("滥用职权", "滥用职权罪"),
    ("玩忽职守", "玩忽职守罪"), ("徇私枉法", "徇私枉法罪"), ("渎职", "渎职罪"),
]

# 民事/行政案由：命中词 → 关键词
_CAUSE_TERMS = [
    ("合同纠纷", "合同纠纷"), ("买卖合同", "买卖合同纠纷"), ("房屋买卖合同", "房屋买卖合同纠纷"),
    ("租赁合同", "租赁合同纠纷"), ("房屋租赁", "房屋租赁合同纠纷"), ("借款合同", "借款合同纠纷"),
    ("民间借贷", "民间借贷纠纷"), ("金融借款", "金融借款合同纠纷"), ("保证合同", "保证合同纠纷"),
    ("建设工程施工合同", "建设工程施工合同纠纷"), ("建设工程价款", "建设工程价款优先受偿权"),
    ("承揽合同", "承揽合同纠纷"), ("运输合同", "运输合同纠纷"), ("服务合同", "服务合同纠纷"),
    ("委托合同", "委托合同纠纷"), ("居间合同", "居间合同纠纷"), ("股权转让", "股权转让纠纷"),
    ("公司决议", "公司决议纠纷"), ("股东知情权", "股东知情权纠纷"), ("股东资格", "股东资格确认纠纷"),
    ("劳动合同", "劳动争议"), ("劳动争议", "劳动争议"), ("工伤保险", "工伤保险待遇纠纷"),
    ("劳务合同", "劳务合同纠纷"), ("劳务派遣", "劳务派遣纠纷"),
    ("机动车交通事故", "机动车交通事故责任纠纷"), ("交通事故", "机动车交通事故责任纠纷"),
    ("医疗损害", "医疗损害责任纠纷"), ("产品责任", "产品责任纠纷"),
    ("财产损害赔偿", "财产损害赔偿纠纷"), ("人身损害赔偿", "人身损害赔偿纠纷"),
    ("名誉权", "名誉权纠纷"), ("肖像权", "肖像权纠纷"), ("隐私权", "隐私权纠纷"),
    ("姓名权", "姓名权纠纷"), ("人格权", "人格权纠纷"),
    ("继承", "继承纠纷"), ("遗嘱", "遗嘱继承纠纷"), ("法定继承", "法定继承纠纷"),
    ("代位继承", "代位继承纠纷"), ("婚姻", "婚姻家庭纠纷"), ("离婚", "离婚纠纷"),
    ("抚养", "抚养纠纷"), ("赡养", "赡养纠纷"), ("扶养", "扶养纠纷"), ("彩礼", "婚约财产纠纷"),
    ("夫妻共同财产", "夫妻共同财产纠纷"), ("同居关系", "同居关系纠纷"),
    ("物权确认", "物权确认纠纷"), ("返还原物", "返还原物纠纷"), ("排除妨害", "排除妨害纠纷"),
    ("相邻关系", "相邻关系纠纷"), ("共有", "共有纠纷"), ("业主", "业主共有权纠纷"),
    ("物业服务", "物业服务合同纠纷"), ("土地承包", "土地承包经营权纠纷"), ("宅基地", "宅基地使用权纠纷"),
    ("征收", "行政征收"), ("拆迁", "房屋拆迁安置补偿合同纠纷"), ("行政协议", "行政协议纠纷"),
    ("行政处罚", "行政处罚"), ("行政复议", "行政复议"), ("行政许可", "行政许可"),
    ("行政强制", "行政强制"), ("国家赔偿", "国家赔偿"),
    ("专利", "专利权纠纷"), ("商标", "商标权纠纷"), ("著作权", "著作权纠纷"),
    ("不正当竞争", "不正当竞争纠纷"), ("商业秘密", "侵犯商业秘密纠纷"),
    ("海事", "海事海商纠纷"), ("海商", "海事海商纠纷"), ("保险合同", "保险合同纠纷"),
    ("票据", "票据纠纷"), ("证券", "证券纠纷"), ("担保物权", "担保物权纠纷"),
    ("抵押权", "抵押权纠纷"), ("质权", "质权纠纷"), ("人民调解", "人民调解"),
    ("独立保函", "独立保函纠纷"), ("保函欺诈", "独立保函欺诈"), ("中止支付保函", "保函止付"),
]

# 程序/量刑特征词
_PROC_TERMS = [
    "再审", "改判", "无罪", "自首", "立功", "缓刑", "假释", "累犯", "数罪并罚",
    "量刑", "上诉", "管辖权异议", "执行异议", "执行复议", "执行监督", "财产保全",
    "认罪认罚", "调解", "撤诉", "强制执行", "带租拍卖", "宣告无罪", "驳回起诉",
    "强制医疗",
]

# 行政/执行标记词（用于部门法标签）
_ADMIN_MARK = ("行政", "处罚决定", "复议机关", "许可证", "强制拆除", "征收决定")
_EXEC_MARK = ("执行异议", "执行复议", "执行监督", "申请执行", "强制执行", "执行程序")


def clean_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub("\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_index(index_csv: Path) -> list[dict]:
    if not index_csv.exists():
        return []
    with index_csv.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_rmfy(cases_dir: Path, index: list[dict]) -> list[dict]:
    url_map = {r.get("id", ""): r.get("url", "") for r in index}
    records = []
    for p in sorted(cases_dir.glob("case_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {p} 解析失败: {exc}", file=sys.stderr)
            continue
        records.append({
            "id": p.stem, "source": "人民法院案例库",
            "title": d.get("title", ""), "category": d.get("type_name", ""),
            "case_no": d.get("ajzh", ""), "keywords": d.get("keyword") or [],
            "date": d.get("zs_date", ""), "url": url_map.get(d.get("id", ""), ""),
            "text": clean_text(d.get("text", "")),
        })
    return records


def _parse_sfb(cases_dir: Path, index: list[dict] | None = None) -> list[dict]:
    records = []
    for p in sorted(cases_dir.glob("case_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {p} 解析失败: {exc}", file=sys.stderr)
            continue
        records.append({
            "id": p.stem, "source": "司法部案例库",
            "title": d.get("title", ""), "category": d.get("type", ""),
            "case_no": d.get("num", ""), "keywords": [],
            "date": d.get("date", ""), "url": d.get("url", ""),
            "text": clean_text(d.get("body", "")),
        })
    return records


def _section_keywords(text: str, section: str) -> list[str]:
    m = re.search(rf"【{section}】\s*(.+?)(?:\n\n|【|$)", text, re.S)
    if not m:
        return []
    return [t for t in _WS_RE.split(m.group(1).strip()) if t]


def _parse_jcy(batch_md: Path, index: list[dict]) -> list[dict]:
    batch = (_BATCH_RE.search(batch_md.name) or [None, ""])[1]
    meta = {r.get("检例编号", ""): r
            for r in index
            if (_BATCH_RE.search(r.get("批次", "") or "") or [None, ""])[1] == batch}
    blocks = _HEADING_RE.split(batch_md.read_text(encoding="utf-8-sig"))
    records = []
    for i in range(1, len(blocks), 3):
        loc = f"检例第{blocks[i].strip()}号"
        m = meta.get(loc, {})
        records.append({
            "id": loc, "source": "最高检指导性案例",
            "title": blocks[i + 1].strip() or "", "category": f"第{batch}批",
            "case_no": "", "keywords": _section_keywords(blocks[i + 2], "关键词"),
            "date": m.get("发布时间", ""), "url": m.get("来源URL", ""),
            "text": clean_text(blocks[i + 2]),
        })
    return records


def _parse_jcy_batches(dir_: Path, index: list[dict]) -> list[dict]:
    records = []
    for p in sorted(dir_.glob("第*批*.md")):
        records.extend(_parse_jcy(p, index))
    return records


def _parse_zgfy(md: Path, index: list[dict]) -> dict:
    num = int(re.search(r"(\d+)", md.stem).group(1))
    meta = next((r for r in index if str(r.get("编号", "")).strip() == str(num)), {})
    text = md.read_text(encoding="utf-8-sig")
    keywords = []
    for line in text.splitlines():
        if line.startswith("关键词"):
            keywords = [t for t in _WS_RE.split(line[len("关键词"):].strip()) if t]
            break
    batch = meta.get("批次", "")
    if batch and not batch.startswith("第"):
        batch = f"第{batch}批"
    return {
        "id": f"指导性案例{num:03d}号", "source": "最高法指导性案例",
        "title": meta.get("标题", "") or md.stem, "category": batch or f"第{meta.get('批次', '')}批",
        "case_no": "", "keywords": keywords,
        "date": meta.get("日期", ""), "url": meta.get("来源URL", ""),
        "text": clean_text(text),
    }


def _parse_zgfy_batches(dir_: Path, index: list[dict]) -> list[dict]:
    return [_parse_zgfy(p, index) for p in sorted(dir_.glob("指导性案例*.md"))]


def _derive_keywords(title: str, text: str, source: str) -> list[str]:
    """关键词为空时，按 标题 + 原文 推导：部门法标签 + 罪名/案由 + 高频概念/程序词。"""
    hay = f"{title}\n{text}"
    cands: list[str] = []

    def hit(term: str) -> bool:
        return term in hay

    # 罪名（标题优先，再按原文；司法部调解案例跳过，防合同条款误标）
    if source != "司法部案例库":
        for term, kw in sorted(_CRIME_TERMS, key=lambda x: -len(x[1])):
            if term in title and kw not in cands:
                cands.append(kw)
        for term, kw in sorted(_CRIME_TERMS, key=lambda x: -len(x[1])):
            if term in text and kw not in cands:
                cands.append(kw)

    # 案由（标题优先，再按原文）
    for term, kw in sorted(_CAUSE_TERMS, key=lambda x: -len(x[1])):
        if term in title and kw not in cands:
            cands.append(kw)
    for term, kw in sorted(_CAUSE_TERMS, key=lambda x: -len(x[1])):
        if term in text and kw not in cands:
            cands.append(kw)

    # 程序/量刑词（原文计数，取出现次数多者）
    proc = sorted(
        (t for t in _PROC_TERMS if t in text and t not in cands),
        key=lambda t: (-text.count(t), -len(t)),
    )
    cands.extend(proc)

    # 重叠去重（长词优先保留，子串关系只留长者）
    kws: list[str] = []
    for kw in sorted(cands, key=len, reverse=True):
        if not any(kw == k or kw in k or k in kw for k in kws):
            kws.append(kw)
    order = {k: i for i, k in enumerate(cands)}
    kws.sort(key=lambda k: order[k])

    # 部门法标签放最前
    tag = None
    if (source != "司法部案例库" and any(hit(t) for t, _ in _CRIME_TERMS)) or \
            "有期徒刑" in text or "判处" in text or "强制医疗" in hay:
        tag = "刑事"
    elif hit("国家赔偿"):
        tag = "国家赔偿"
    elif any(hit(m) for m in _EXEC_MARK):
        tag = "执行"
    elif any(hit(m) for m in _ADMIN_MARK) or hit("行政"):
        tag = "行政"
    elif any(hit(t) for t, _ in _CAUSE_TERMS) or "纠纷" in title or "民事" in text:
        tag = "民事"
    elif source == "司法部案例库":
        tag = "民事"
    if tag:
        kws.insert(0, tag)

    return kws[:6]


def main(argv=None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description="案例库统一格式化")
    ap.add_argument("--data", default=str(repo_root / "data/案例数据"))
    ap.add_argument("--out", default=str(repo_root / "data/案例库统一"))
    args = ap.parse_args(argv)

    src = Path(args.data)
    out = Path(args.out)
    docs = out / "documents"
    docs.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("人民法院案例库", _parse_rmfy, src / "人民法院案例库/cases",
         src / "人民法院案例库/index.csv"),
        ("司法部案例库", _parse_sfb, src / "司法部案例库/cases", None),
        ("最高检指导性案例", _parse_jcy_batches, src / "最高检指导性案例",
         src / "最高检指导性案例/index.csv"),
        ("最高法指导性案例", _parse_zgfy_batches, src / "最高法指导性案例",
         src / "最高法指导性案例/index.csv"),
    ]

    all_records = []
    for source, fn, data_path, index_path in jobs:
        index = _read_index(index_path) if index_path else []
        records = fn(data_path, index)
        for r in records:
            if not r["keywords"]:
                r["keywords"] = _derive_keywords(r["title"], r["text"], r["source"])
        print(f"OK: {source} {len(records)} 条")
        all_records.extend(records)

    with (out / "index.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["定位符", "来源库", "标题", "类别", "案号", "关键词",
                         "日期", "url", "文档文件"])
        for r in all_records:
            writer.writerow([
                r["id"], r["source"], r["title"], r["category"], r["case_no"],
                " ".join(r["keywords"]), r["date"], r["url"],
                f"documents/{r['source']}.jsonl",
            ])

    for source in CASE_SOURCES:
        recs = [r for r in all_records if r["source"] == source]
        with (docs / f"{source}.jsonl").open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"OK: 共 {len(all_records)} 条 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
