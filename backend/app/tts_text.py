"""朗读文本归一化：只做确定性、无歧义的替换，不改写语义。

原则（依据 2026-09-20 实测）：
- 【标签】与《法条名》原样保留：千问 TTS 会跳过方括号/书名号本身，但会朗读其中的内容，
  删掉反而丢失「法名 + 考点」的听觉锚点；
- 只处理会被念错或在听感上突兀的符号（≥ ≤ ～ ％ ×）与 Markdown 残留；
- 不改写数字、法条号、英文术语（实测中英混排朗读正常）；
- 保证幂等：normalize(normalize(x)) == normalize(x)。
"""
import re

_MARKDOWN_CHARS = "*_`>|"
_SYMBOLS = {
    "≥": "大于等于", "≤": "小于等于", "≈": "约",
    "～": "至", "~": "至", "％": "%", "×": "乘", "&": "和", "＆": "和",
}
_DROP_CHARS = "「」『』“”"
_WS = re.compile(r"[ \t\u3000]+")
_CJK = r"\u4e00-\u9fff"
_END_PUNCT = "。！？!?…"


def normalize(text: str) -> str:
    """把条目 tts_text 归一为朗读友好文本（幂等，不做语义改写）。"""
    if not text:
        return ""
    out = text.replace("\r", "").replace("\n", " ")
    out = out.translate({ord(ch): None for ch in _MARKDOWN_CHARS})
    out = out.translate({ord(ch): None for ch in _DROP_CHARS})
    for src, dst in _SYMBOLS.items():
        out = out.replace(src, dst)
    out = _WS.sub(" ", out).strip()
    # 中文之间的空格纯属排版噪音，去掉；英文术语内部的空格保留
    out = re.sub(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])", "", out)
    for _ in range(2):
        out = re.sub(rf"(?<=[{_CJK}]) +", "", out)
        out = re.sub(rf" +(?=[{_CJK}])", "", out)
    out = out.strip()
    if out and out[-1] not in _END_PUNCT:
        out += "。"
    return out
