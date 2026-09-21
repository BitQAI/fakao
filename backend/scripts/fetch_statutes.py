"""法条元信息抓取：从国家法律法规数据库取法名、bbbs、公布日、施行日、效力状态。

**全文下载不可用**：正文托管在内网 OSS（flkoss.obs-bj2-internal.cucloud.cn，
公网 DNS 解析到保留段 198.18.0.149），公网桶为私有且签名按内网 host 签发；
预览走 OFD 阅读器但 file= 参数同样指向内网地址（172.16.x.x）。
因此正文由 normalize_statutes.py 从投递目录归一，本脚本只产出元信息。

用法：
    python scripts/fetch_statutes.py                  # 全量抓元信息
    python scripts/fetch_statutes.py --only 商标法
    python scripts/fetch_statutes.py --list           # 只看目标清单
    python scripts/fetch_statutes.py --for-year 2027  # 版本选取的备考年度（默认 2027）

产物：data/法条库/_meta.json
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402

BASE = "https://flk.npc.gov.cn"
SEARCH_API = f"{BASE}/law-search/search/list"
DETAIL_API = f"{BASE}/law-search/search/flfgDetails"
_TAG_RE = re.compile(r"<[^>]+>")


def clean_title(title: str) -> str:
    """搜索接口会在标题里插入 <em class='highlight'> 高亮标签，比对前必须剥掉。"""
    return _TAG_RE.sub("", title or "").strip()
HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "Referer": f"{BASE}/",
    "User-Agent": "Mozilla/5.0",
}

#: 目标清单：(检索词, 归类)。归类见 SPEC 4.1 与审计修正。
TARGETS: list[tuple[str, str]] = [
    # 法律本体 —— 考查表缺口
    ("中华人民共和国劳动法", "法律"), ("中华人民共和国劳动合同法", "法律"),
    ("中华人民共和国社会保险法", "法律"), ("中华人民共和国劳动争议调解仲裁法", "法律"),
    ("中华人民共和国著作权法", "法律"), ("中华人民共和国专利法", "法律"),
    ("中华人民共和国商标法", "法律"),
    ("中华人民共和国反垄断法", "法律"), ("中华人民共和国反不正当竞争法", "法律"),
    ("中华人民共和国消费者权益保护法", "法律"), ("中华人民共和国产品质量法", "法律"),
    ("中华人民共和国食品安全法", "法律"),
    ("中华人民共和国土地管理法", "法律"), ("中华人民共和国城市房地产管理法", "法律"),
    ("中华人民共和国环境影响评价法", "法律"), ("中华人民共和国环境保护税法", "法律"),
    ("中华人民共和国法官法", "法律"), ("中华人民共和国检察官法", "法律"),
    ("中华人民共和国律师法", "法律"), ("中华人民共和国公证法", "法律"),
    ("中华人民共和国公务员法", "法律"), ("中华人民共和国海商法", "法律"),
    ("中华人民共和国个人独资企业法", "法律"), ("中华人民共和国外商投资法", "法律"),
    ("中华人民共和国涉外民事关系法律适用法", "法律"),
    ("中华人民共和国全国人民代表大会和地方各级人民代表大会选举法", "法律"),
    ("中华人民共和国香港特别行政区基本法", "法律"),
    ("中华人民共和国澳门特别行政区基本法", "法律"),
    ("中华人民共和国香港特别行政区驻军法", "法律"),
    ("中华人民共和国澳门特别行政区驻军法", "法律"),
    ("中华人民共和国外国国家豁免法", "法律"),
    ("中华人民共和国引渡法", "法律"), ("中华人民共和国缔结条约程序法", "法律"),
    ("中华人民共和国法律援助法", "法律"),
    # 新增大纲法（是否已颁布待核实）
    ("中华人民共和国治安管理处罚法", "法律"), ("中华人民共和国生态环境法典", "法律"),
    ("中华人民共和国民族团结进步促进法", "法律"),
    ("中华人民共和国国家发展规划法", "法律"),
    # 配套法规
    ("工伤保险条例", "行政法规"),
    ("职工带薪年休假条例", "行政法规"),
    ("女职工劳动保护特别规定", "行政法规"),
    ("中华人民共和国政府信息公开条例", "行政法规"),
    ("中华人民共和国反倾销条例", "行政法规"),
    ("中华人民共和国反补贴条例", "行政法规"),
    ("中华人民共和国保障措施条例", "行政法规"),
    ("知识产权海关保护条例", "行政法规"),
    ("中华人民共和国专利法实施细则", "行政法规"),
    ("最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（二）", "司法解释"),
    ("最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释", "司法解释"),
    ("最高人民法院关于审理民间借贷案件适用法律若干问题的规定", "司法解释"),
    ("最高人民法院关于适用《中华人民共和国民法典》时间效力的若干规定", "司法解释"),
    # 国际条约（flk 为法律法规数据库，条约多半不在其中，抓不到会记为 found=false）
    ("联合国国际货物销售合同公约", "国际条约"),
    ("联合国海洋法公约", "国际条约"),
    ("维也纳外交关系公约", "国际条约"),
    ("维也纳条约法公约", "国际条约"),
    ("维也纳领事关系公约", "国际条约"),
    ("联合国宪章", "国际条约"),
    ("保护文学和艺术作品伯尔尼公约", "国际条约"),
    ("保护工业产权巴黎公约", "国际条约"),
    ("承认及执行外国仲裁裁决公约", "国际条约"),
    ("国际法院规约", "国际条约"),
]


def _request(url: str, payload: dict | None = None, retries: int = 3) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {url}: {last}")


def search(keyword: str, size: int = 20, search_type: int = 1) -> list[dict]:
    """检索候选版本行。

    searchType=1 是标题精确检索（推荐）；2 是全文模糊检索，会把「治安管理处罚法」
    匹配成 10350 条无关结果，只能作为兜底。
    """
    body = {"searchRange": 1, "searchType": search_type, "searchContent": keyword,
            "page": 1, "size": size, "sxrq": [], "gbrq": [], "sxx": [],
            "gbrqYear": [], "flfgCodeId": [], "zdjgCodeId": []}
    return _request(SEARCH_API, body).get("rows") or []


def detail(bbbs: str) -> dict:
    """取单部法的元信息（不含正文）。"""
    resp = _request(f"{DETAIL_API}?bbbs={bbbs}")
    return resp.get("data") or {}


def _pick_version(rows: list[dict], keyword: str, for_year: int) -> dict | None:
    """版本选取：标题精确匹配优先；已施行取施行日最新，否则取最早的未来版本。"""
    exact = [r for r in rows if clean_title(r.get("title")) == keyword]
    pool = exact or [r for r in rows if keyword in clean_title(r.get("title"))]
    if not pool:
        return None
    cutoff = f"{for_year}-09-01"
    effective = [r for r in pool if (r.get("sxrq") or "") <= cutoff]
    if effective:
        return max(effective, key=lambda r: r.get("sxrq") or "")
    return min(pool, key=lambda r: r.get("sxrq") or "")


def search_terms(keyword: str) -> list[str]:
    """检索词：官方站是分词匹配，用全名（如「中华人民共和国商标法」）会先命中
    「中华人民共和国宪法」一串，反而搜不到目标。故优先用去掉国名前缀的短名。"""
    terms = [keyword]
    short = keyword.replace("中华人民共和国", "").strip()
    if short and short != keyword:
        terms.insert(0, short)
    return terms


def fetch_one(keyword: str, category: str, for_year: int) -> dict:
    rows: list[dict] = []
    chosen = None
    for term in search_terms(keyword):
        for search_type in (1, 2):
            rows = search(term, search_type=search_type)
            chosen = _pick_version(rows, keyword, for_year)
            if chosen is not None:
                break
        if chosen is not None:
            break
    if chosen is None:
        return {"keyword": keyword, "category": category, "found": False,
                "candidates": 0}
    meta = detail(chosen["bbbs"])
    return {
        "keyword": keyword, "category": category, "found": True,
        "candidates": len(rows),
        "title": clean_title(chosen["title"]), "bbbs": chosen["bbbs"],
        "公布日期": chosen.get("gbrq", ""), "施行日期": chosen.get("sxrq", ""),
        "效力状态": chosen.get("sxx"),
        "制定机关": chosen.get("zdjgName", ""), "法律性质": chosen.get("flxz", ""),
        "ossFile": (meta.get("ossFile") or {}),
        "其他版本": [{"title": clean_title(r["title"]), "bbbs": r["bbbs"],
                      "公布日期": r.get("gbrq"), "施行日期": r.get("sxrq"),
                      "效力状态": r.get("sxx")}
                     for r in rows if r["bbbs"] != chosen["bbbs"]][:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取法条元信息（不含正文）")
    ap.add_argument("--only", help="只抓某个检索词")
    ap.add_argument("--list", action="store_true", help="只打印目标清单")
    ap.add_argument("--for-year", type=int, default=2027,
                    help="备考年度，用于版本选取（默认 2027）")
    args = ap.parse_args()

    targets = TARGETS
    if args.only:
        targets = [t for t in TARGETS if args.only in t[0]]
    if args.list:
        for kw, cat in targets:
            print(f"{cat:<8}{kw}")
        print(f"共 {len(targets)} 项")
        return 0

    out: dict[str, dict] = {}
    meta_path = config.STATUTE_DIR / "_meta.json"
    if meta_path.exists():
        out = json.loads(meta_path.read_text(encoding="utf-8")).get("items", {})

    for i, (kw, cat) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {kw}", flush=True)
        try:
            out[kw] = fetch_one(kw, cat, args.for_year)
            flag = "命中" if out[kw]["found"] else "未收录"
            extra = ""
            if out[kw]["found"]:
                extra = (f"  {out[kw]['title']} | 施行 {out[kw]['施行日期']}"
                         f" | 候选 {out[kw]['candidates']}")
            print(f"    {flag}{extra}")
        except RuntimeError as exc:
            out[kw] = {"keyword": kw, "category": cat, "found": False,
                       "error": str(exc)}
            print(f"    失败：{exc}")
        time.sleep(0.4)

    config.STATUTE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"for_year": args.for_year, "count": len(out), "items": out}
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    hit = sum(1 for v in out.values() if v.get("found"))
    print(f"\n完成：{hit}/{len(out)} 命中，写入 {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
