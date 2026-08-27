import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from match_cases import entry_terms, score_case  # noqa: E402


def test_entry_terms_specific():
    e = {"point": "转化型抢劫", "submodule": "分则-财产犯罪",
         "anchor": "窃贼入户盗得现金，为抗拒抓捕持刀威胁",
         "conclusion": "转化为抢劫罪，按抢劫罪处罚。"}
    terms, specific = entry_terms(e)
    assert "转化型抢劫" in specific
    assert "抢劫罪" in specific
    assert "抗拒抓捕" in terms


def test_score_case_requires_specific_text_hit():
    terms = ["抢劫罪", "转化型抢劫", "抗拒抓捕"]
    specific = ["转化型抢劫", "抢劫罪"]
    good = score_case(terms, specific, "邓某周抢劫案",
                      "刑事 转化型抢劫 盗窃 抗拒抓捕",
                      "正文提到转化型抢劫与抗拒抓捕，定抢劫罪。")
    assert good[0] >= 6 and good[2] >= 1
    bad = score_case(terms, ["转化型抢劫"], "谭某勇抢劫案",
                     "刑事 抢劫罪 死缓 申诉",
                     "正文只提到抢劫罪这一罪名，未涉及转化情形。")
    assert bad[2] == 0
