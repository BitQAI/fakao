import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from match_cases import (case_domain, entry_terms, main, score_case,
                         subject_allows_domain)  # noqa: E402


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


def _write_fixtures(tmp_path):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    (entries_dir / "刑法.json").write_text(json.dumps({
        "schema": "fakao-entry/1.0", "entries": [{
            "id": "XF-999", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": "转化型抢劫", "anchor": "窃贼入户盗得现金，为抗拒抓捕持刀威胁",
            "conclusion": "转化为抢劫罪，按抢劫罪处罚。",
            "cases": [{"source": "人民法院案例库", "loc": "case_00001"}],
        }],
    }, ensure_ascii=False), encoding="utf-8")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "最高法指导性案例.jsonl").write_text(
        json.dumps({"source": "最高法指导性案例", "id": "指导性案例225号",
                    "text": "正文提到转化型抢劫与抗拒抓捕，最终以抢劫罪定罪。"},
                   ensure_ascii=False) + "\n", encoding="utf-8")

    index = tmp_path / "index.csv"
    index.write_text(
        "定位符,来源库,标题,类别,案号,关键词,日期,url,文档文件\n"
        "指导性案例225号,最高法指导性案例,邓某周抢劫案,刑事,,"
        "刑事 转化型抢劫 盗窃 抗拒抓捕,,,documents/最高法指导性案例.jsonl\n",
        encoding="utf-8")
    return str(entries_dir), str(index), str(docs)


def test_append_guiding_adds_to_existing_cases(tmp_path):
    entries, index, docs = _write_fixtures(tmp_path)
    assert main(["--entries", entries, "--index", index, "--docs", docs,
                 "--append-guiding"]) == 0
    payload = json.loads(Path(entries, "刑法.json").read_text(encoding="utf-8"))
    cases = payload["entries"][0]["cases"]
    assert len(cases) == 2
    assert {"source": "最高法指导性案例", "loc": "指导性案例225号"} in cases


def test_append_guiding_is_idempotent(tmp_path):
    entries, index, docs = _write_fixtures(tmp_path)
    main(["--entries", entries, "--index", index, "--docs", docs,
          "--append-guiding"])
    main(["--entries", entries, "--index", index, "--docs", docs,
          "--append-guiding"])
    payload = json.loads(Path(entries, "刑法.json").read_text(encoding="utf-8"))
    cases = payload["entries"][0]["cases"]
    assert len(cases) == 2  # 二次运行不重复追加


def test_plain_mode_skips_entries_with_cases(tmp_path):
    entries, index, docs = _write_fixtures(tmp_path)
    assert main(["--entries", entries, "--index", index, "--docs", docs]) == 0
    payload = json.loads(Path(entries, "刑法.json").read_text(encoding="utf-8"))
    assert len(payload["entries"][0]["cases"]) == 1  # 保持原样


def test_case_domain_detection():
    assert case_domain("刑事 正当防卫 未成年人") == "刑事"
    assert case_domain("刑事/正当防卫/未成年人") == "刑事"
    assert case_domain("民事 继承纠纷") == "民事"
    assert case_domain("知识产权 专利") == "知识产权"
    assert case_domain("行政 处罚") == "行政"
    assert case_domain("") is None


def test_subject_allows_domain():
    assert subject_allows_domain("刑法", "分则-财产犯罪", "刑事")
    assert not subject_allows_domain("刑法", "分则-财产犯罪", "民事")
    assert subject_allows_domain("民法", "婚姻家庭", "民事")
    assert subject_allows_domain("商经知", "专利法", "知识产权")
    assert subject_allows_domain("三国法", "国际私法-冲突规范", "民事")
    assert not subject_allows_domain("三国法", "国家承认与继承", "民事")
    assert not subject_allows_domain("理论法", "中国法制史", "民事")


def test_append_guiding_respects_domain_gate(tmp_path):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    (entries_dir / "三国法.json").write_text(json.dumps({
        "schema": "fakao-entry/1.0", "entries": [{
            "id": "SG-999", "subject": "三国法", "submodule": "国家承认与继承",
            "point": "国家承认的宣示说", "anchor": "某国承认新国家",
            "conclusion": "承认是宣示性行为。", "cases": [],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "最高法指导性案例.jsonl").write_text(
        json.dumps({"source": "最高法指导性案例", "id": "指导性案例050号",
                    "text": "继承纠纷正文，涉及法定继承顺序。"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    index = tmp_path / "index.csv"
    index.write_text(
        "定位符,来源库,标题,类别,案号,关键词,日期,url,文档文件\n"
        "指导性案例050号,最高法指导性案例,某继承案,民事,,"
        "民事 继承 法定继承,,,documents/最高法指导性案例.jsonl\n",
        encoding="utf-8")
    assert main(["--entries", str(entries_dir), "--index", str(index),
                 "--docs", str(docs), "--append-guiding"]) == 0
    payload = json.loads(Path(entries_dir, "三国法.json").read_text(encoding="utf-8"))
    assert payload["entries"][0]["cases"] == []  # 国际公法条目不挂民事案例
