"""关系型判断题闸门：情态词 / 程序层级 / 易混概念对的可核验校验。

与 `app.number_terms` 并列，是判断题的第二道闸门（数字题查数字，关系题查关系词）：

- answer=对：题干里的关系词必须**全部**能在依据原文（法条正文 / 条目场景+结论）中找到；
- answer=错：题干相对原文有且**仅有 1 处**关系词被偷换，且该偷换必须落在 SWAPS 白名单内
  （即原文恰好少了这个词、题干恰好多了那个词）；
- 主体一致：题干里的机关/主体名必须在原文命中（原文没有主体名时不判）；
- 不抄原文：**「对」题**与原文任一单句相似度 ≥ min_ratio（默认 0.95，即近似逐字照抄）
  视为抄写，丢弃（「错」题与原文只差一个词，天然高度相似，不做此判）。

词表与白名单是**数据**不是逻辑：新增词族只改 FAMILIES / SWAPS，不动校验代码。
"""
import re
from difflib import SequenceMatcher

#: 17 个词族（长词优先匹配，避免「重审」吃掉「发回重审」）
FAMILIES: dict[str, tuple[str, ...]] = {
    "modal": ("可以", "应当", "必须", "不得", "无须", "无需"),
    "authority": ("自行决定", "有权", "无权", "报请", "批准", "备案"),
    "form": ("决定", "决议", "裁定", "判决", "命令"),
    "effect": ("可撤销", "效力待定", "撤销", "撤回", "解除", "终止", "无效", "不成立"),
    "review": ("复议", "复核"),
    "instance": ("发回重审", "申请再审", "一审", "二审", "再审", "重审", "提审",
                 "申诉", "上诉", "抗诉"),
    "org": ("审判委员会", "法官会议", "合议庭", "独任"),
    "claim": ("反诉", "反驳", "抗辩", "本证", "反证"),
    "outcome": ("驳回诉讼请求", "撤回起诉", "按撤诉处理", "驳回起诉", "不予受理",
                "延期审理", "撤诉", "中止", "终结"),
    "level": ("设区的市级", "上一级", "省级", "县级", "上级", "同级", "本级", "下级"),
    "sanction": ("没收违法所得", "没收财产", "罚金", "罚款", "吊销", "注销"),
    "coercion": ("取保候审", "监视居住", "逮捕", "拘传", "留置"),
    "sentence": ("暂予监外执行", "假释", "减刑", "缓刑"),
    "time": ("除斥期间", "诉讼时效", "上诉期", "抗诉期", "举证期限", "追诉时效"),
    "liability": ("补充责任", "连带责任", "按份责任", "连带", "按份", "定金", "订金",
                  "违约金"),
    "agency": ("善意取得", "表见代理", "无权代理", "无权处分", "推定", "视为"),
    "evidence": ("排除合理怀疑", "高度盖然性", "优势证据", "举证责任倒置",
                 "非法证据排除", "瑕疵证据", "举证责任"),
}

#: 「原文词 -> 允许被偷换成哪些词」；只约束「错」题，且跨族互换也支持
SWAPS: dict[str, tuple[str, ...]] = {
    # 情态 / 权限
    "应当": ("可以", "无须"), "可以": ("应当", "必须"), "必须": ("可以", "应当"),
    "不得": ("可以", "应当"), "无须": ("应当", "必须"), "无需": ("应当", "必须"),
    "自行决定": ("报请", "备案"), "报请": ("自行决定",), "批准": ("备案",),
    "备案": ("批准",), "有权": ("无权",), "无权": ("有权",),
    # 文书形式
    "决定": ("决议", "裁定"), "决议": ("决定",), "裁定": ("判决", "决定"),
    "判决": ("裁定",), "命令": ("决定",),
    # 效力状态
    "撤销": ("撤回",), "撤回": ("撤销",), "解除": ("终止",), "终止": ("解除",),
    "无效": ("可撤销",), "可撤销": ("无效",), "效力待定": ("不成立",),
    "不成立": ("效力待定",),
    # 复议 / 复核
    "复议": ("复核",), "复核": ("复议",),
    # 审级与程序阶段
    "一审": ("二审",), "二审": ("一审",), "再审": ("重审",), "重审": ("再审",),
    "发回重审": ("提审",), "提审": ("发回重审",), "上诉": ("抗诉",), "抗诉": ("上诉",),
    "申诉": ("申请再审",), "申请再审": ("申诉",),
    # 审判组织
    "独任": ("合议庭",), "合议庭": ("独任", "审判委员会"),
    "审判委员会": ("合议庭",), "法官会议": ("审判委员会",),
    # 诉与证明
    "反诉": ("抗诉", "反驳"), "反驳": ("反诉",), "抗辩": ("反驳",),
    "本证": ("反证",), "反证": ("本证",),
    # 诉讼行为结果
    "撤回起诉": ("驳回起诉",), "撤诉": ("撤回起诉",), "按撤诉处理": ("撤诉",),
    "驳回起诉": ("驳回诉讼请求", "不予受理"), "驳回诉讼请求": ("驳回起诉",),
    "不予受理": ("驳回起诉",), "中止": ("终结",), "终结": ("中止",),
    "延期审理": ("中止",),
    # 层级
    "上一级": ("本级",), "上级": ("同级",), "同级": ("上级",), "本级": ("上一级",),
    "下级": ("上级",), "省级": ("设区的市级",), "设区的市级": ("县级",),
    "县级": ("设区的市级",),
    # 处罚与强制措施
    "罚金": ("罚款",), "罚款": ("罚金",), "吊销": ("注销",), "注销": ("吊销",),
    "没收财产": ("没收违法所得",), "没收违法所得": ("没收财产",),
    "取保候审": ("监视居住",), "监视居住": ("取保候审",),
    "逮捕": ("拘传", "留置"), "拘传": ("逮捕",), "留置": ("逮捕",),
    # 刑罚执行
    "假释": ("减刑", "缓刑"), "减刑": ("假释",), "缓刑": ("假释",),
    "暂予监外执行": ("假释",),
    # 期间
    "诉讼时效": ("除斥期间",), "除斥期间": ("诉讼时效",),
    "上诉期": ("抗诉期",), "抗诉期": ("上诉期",), "举证期限": ("上诉期",),
    # 责任形态
    "连带": ("按份",), "按份": ("连带",), "补充责任": ("连带",),
    "连带责任": ("补充责任",), "定金": ("订金",), "订金": ("定金",),
    "违约金": ("定金",),
    # 代理与物权
    "善意取得": ("表见代理",), "表见代理": ("善意取得",),
    "无权代理": ("无权处分",), "无权处分": ("无权代理",),
    "推定": ("视为",), "视为": ("推定",),
    # 证据
    "排除合理怀疑": ("高度盖然性",), "高度盖然性": ("排除合理怀疑",),
    "优势证据": ("高度盖然性",), "非法证据排除": ("瑕疵证据",),
    "瑕疵证据": ("非法证据排除",), "举证责任倒置": ("举证责任",),
}

#: 词族稀有度（越靠前越优先分配 variant，避免全库都是 modal）
FAMILY_ORDER: tuple[str, ...] = (
    "evidence", "time", "sentence", "org", "claim", "liability", "review", "agency",
    "coercion", "outcome", "instance", "sanction", "level", "effect", "authority",
    "form", "modal",
)

#: 机关/主体名；「委员会/机关/单位」过泛，不作为主体判据
SUBJECT_RE = re.compile(
    r"最高人民法院|高级人民法院|中级人民法院|基层人民法院|人民法院|人民检察院|"
    r"公安机关|国家安全机关|司法行政机关|监察机关|人民政府|国务院|仲裁委员会|"
    r"股东会|股东大会|董事会|监事会|审判委员会|检察委员会|村民委员会|居民委员会|"
    r"委员会|政府|机关")
GENERIC_SUBJECTS = {"委员会", "政府", "机关"}

_PATTERNS = {name: re.compile("|".join(
    re.escape(t) for t in sorted(terms, key=len, reverse=True)))
    for name, terms in FAMILIES.items()}
_SENT_SPLIT_RE = re.compile(r"[。；!？?\n]")
_PUNCT_RE = re.compile(r"[，。、；:：\"'（）()《》\s]")
#: 这些词里的「有权」不是权限考点（所有权/使用权/股权…），扫描前等长遮蔽
_MASK_RE = re.compile(r"所有权|使用权|经营权|知识产权|债权|股权|物权|股票期权")


def _spans(text: str) -> list[tuple[int, int, str, str]]:
    """抽取 [(起, 止, 族名, 词)]，含重叠候选。"""
    text = _MASK_RE.sub(lambda m: "※" * len(m.group(0)), text or "")
    out: list[tuple[int, int, str, str]] = []
    for name, rx in _PATTERNS.items():
        for m in rx.finditer(text):
            out.append((m.start(), m.end(), name, m.group(0)))
    return out


def _drop_contained(spans: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    """丢掉被更长命中完全包含的短词（「发回重审」内的「重审」不再单独计）；
    完全同位置的重复命中只留第一个。"""
    kept: list[tuple[int, int, str, str]] = []
    for i, (start, end, _name, _term) in enumerate(spans):
        dropped = False
        for j, other in enumerate(spans):
            if i == j:
                continue
            o_start, o_end = other[0], other[1]
            longer_and_wraps = (o_start <= start and end <= o_end
                                and (o_end - o_start) > (end - start))
            same_span_earlier = (o_start, o_end) == (start, end) and j < i
            if longer_and_wraps or same_span_earlier:
                dropped = True
                break
        if not dropped:
            kept.append(spans[i])
    return kept


def extract(text: str) -> set[tuple[str, str]]:
    """抽取 {(族名, 词)}；长词优先，包含关系只留最长命中。"""
    return {(name, term) for _start, _end, name, term in _drop_contained(_spans(text))}


def terms_of(text: str) -> set[str]:
    return {term for _family, term in extract(text)}


def families_of(text: str) -> list[str]:
    """命中词族，按 FAMILY_ORDER 稀有度排序（供 variant 分配）。"""
    hit = {family for family, _term in extract(text)}
    return [f for f in FAMILY_ORDER if f in hit]


def swaps_for(term: str) -> tuple[str, ...]:
    return SWAPS.get(term, ())


def subject_terms(text: str) -> set[str]:
    return {m.group(0) for m in SUBJECT_RE.finditer(text or "")} - GENERIC_SUBJECTS


def similarity(stem: str, sentence: str) -> float:
    a = _PUNCT_RE.sub("", stem or "")
    b = _PUNCT_RE.sub("", sentence or "")
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def max_sentence_similarity(stem: str, reference: str) -> float:
    """题干与依据原文**任一单句**的最大相似度（整段比对会被长文稀释）。"""
    best = 0.0
    for sentence in _SENT_SPLIT_RE.split(reference or ""):
        if len(sentence) < 8:
            continue
        best = max(best, similarity(stem, sentence))
    return best


def check(stem: str, reference: str, answer: str,
          min_ratio: float = 0.95) -> tuple[bool, str]:
    """关系型判断题闸门。返回 (是否通过, 原因)。"""
    stem_terms = extract(stem)
    if not stem_terms:
        return False, "题干无关系词"
    ref_terms = extract(reference)
    extra = stem_terms - ref_terms
    if answer == "对":
        if extra:
            return False, "「对」题含原文外关系词：" + "、".join(
                sorted(term for _f, term in extra))
    elif answer == "错":
        if not extra:
            return False, "「错」题未偷换关系词"
        if len(extra) > 1:
            return False, f"「错」题偷换 {len(extra)} 处关系词（上限 1）"
        missing = ref_terms - stem_terms
        if len(missing) > 1:
            return False, f"「错」题改动 {len(missing)} 处关系词（上限 1）"
        if not missing:
            return False, "「错」题新增了原文没有的关系词"
        new_term = next(iter(extra))[1]
        old_term = next(iter(missing))[1]
        if new_term not in swaps_for(old_term):
            return False, f"不允许把「{old_term}」偷换成「{new_term}」"
    else:
        return False, "答案必须是「对」或「错」"
    unmatched = subject_terms(stem) - subject_terms(reference)
    if unmatched:
        return False, "题干主体未在原文出现：" + "、".join(sorted(unmatched))
    if answer == "对":
        ratio = max_sentence_similarity(stem, reference)
        if ratio >= min_ratio:
            return False, f"「对」题与原文单句相似度 {ratio:.2f}（疑似抄原文）"
    return True, ""
