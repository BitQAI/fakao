from app.tts_text import normalize


def test_normalize_keeps_tags_and_law_names():
    """【标签】与《法条名》保留：它们是听觉锚点，实测 TTS 会朗读其内容。"""
    text = "【环境保护法·水污染防治】某企业改建项目增加排污量。"
    assert normalize(text) == text


def test_normalize_replaces_risky_symbols():
    assert normalize("≥37日。") == "大于等于37日。"
    assert normalize("≤5年。") == "小于等于5年。"
    assert normalize("3~5人。") == "3至5人。"
    assert normalize("占比40％左右。") == "占比40%左右。"
    assert normalize("2×3。") == "2乘3。"
    assert normalize("甲乙＆丙丁。") == "甲乙和丙丁。"


def test_normalize_strips_markdown_and_quotes():
    assert normalize("**重点**：`刑诉法`第91条。") == "重点：刑诉法第91条。"
    assert normalize("「正当防卫」成立。") == "正当防卫成立。"
    assert normalize("> 引用的条文。") == "引用的条文。"


def test_normalize_collapses_layout_spaces():
    assert normalize("甲  乙\u3000丙。") == "甲乙丙。"
    # 中文相邻的空格是排版噪音（去掉），拉丁词之间的空格保留
    assert normalize("Incoterms 2020 中 DPU 术语。") == "Incoterms 2020中DPU术语。"
    assert normalize("依据民法典 第188条。") == "依据民法典第188条。"


def test_normalize_appends_final_punctuation():
    assert normalize("结论") == "结论。"
    assert normalize("结论！") == "结论！"
    assert normalize("") == ""


def test_normalize_is_idempotent():
    samples = [
        "【刑法-正当防卫】甲反击致乙重伤（≥轻伤）。",
        "**民法典**第188条：3~5年期间。",
        "Incoterms 2020 中的 CIP 与 CIF。",
        "甲  乙",
    ]
    for s in samples:
        once = normalize(s)
        assert normalize(once) == once
