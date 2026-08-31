#!/usr/bin/env python
"""法考冲刺工具 e2e 冒烟测试（Playwright，前端 :3001 / 后端 :8090）。

运行：
  /Users/huajun/.hermes/venv/bin/python frontend/e2e/smoke_test.py
截图输出到 frontend/e2e/shots/。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:3001"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

errors: list[str] = []


def shot(page, name: str):
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def check(cond: bool, msg: str):
    if not cond:
        errors.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(f"  ✓ {msg}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 420, "height": 860},
                                device_scale_factor=2)
        page.on("console", lambda m: errors.append(f"console:{m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))

        # 1. 今日页
        print("== 今日页 ==")
        page.goto(BASE + "/", wait_until="networkidle")
        check(page.locator("h1", has_text="今日").count() > 0, "今日标题")
        check(page.locator(".progress-ring").count() > 0, "进度环")
        check(page.locator(".counts .count").count() == 4, "计划四计数")
        shot(page, "01-today")

        # 2. 看背
        print("== 看背 ==")
        page.goto(BASE + "/study?view=read", wait_until="networkidle")
        check(page.locator(".flashcard").count() > 0, "闪卡渲染")
        shot(page, "02-read-front")
        page.locator(".flashcard").click()
        page.wait_for_timeout(700)
        check(page.locator(".rate-row").count() > 0, "翻面评分区")
        shot(page, "03-read-back")
        if page.locator(".btn-good").count() > 0:
            page.locator(".btn-good").first.click()
            page.wait_for_timeout(700)
            check(page.locator(".flashcard").count() > 0, "评分后下一张")

        # 3. 听学
        print("== 听学 ==")
        page.goto(BASE + "/study?view=listen", wait_until="networkidle")
        check(page.locator("audio").count() > 0, "音频元素")
        shot(page, "04-listen")
        mark_btn = page.get_by_role("button", name="标记", exact=True)
        if mark_btn.count() > 0:
            mark_btn.click()
            page.wait_for_timeout(500)
            check(page.get_by_role("button", name="已标记 ✓").count() > 0, "听学标记成功")

        # 4. 自测（今日）
        print("== 自测 ==")
        page.goto(BASE + "/study?view=quiz", wait_until="networkidle")
        if page.locator(".option").count() > 0:
            page.locator(".option").first.click()
            page.wait_for_timeout(700)
            check(page.locator(".result").count() > 0, "自测判分")
            shot(page, "05-quiz")

        # 5. 组卷
        print("== 组卷 ==")
        page.get_by_role("button", name="组卷").first.click()
        page.wait_for_timeout(400)
        check(page.locator("h2", has_text="智能组卷").count() > 0, "组卷配置页")
        page.get_by_role("button", name="选择范围并开始").click()
        page.wait_for_timeout(500)
        check(page.locator("b", has_text="自定义学习范围").count() > 0, "范围选择弹层")
        page.get_by_role("button", name="按科目选择（学整科）").click()
        page.wait_for_timeout(300)
        first_subj = page.locator(".pick-item").first
        if first_subj.count() > 0:
            first_subj.click()
            page.get_by_role("button", name="开始学习").click()
            page.wait_for_selector(".option, h3", timeout=25000)
            check(page.locator(".option, h3").count() > 0, "组卷出题")
            shot(page, "06-group-quiz")

        # 6. 错题本
        print("== 错题本 ==")
        page.goto(BASE + "/study?view=wrong", wait_until="networkidle")
        check(page.get_by_text("我的标记").count() > 0, "错题页我的标记")
        shot(page, "07-wrongbook")

        # 7. 报告-统计
        print("== 报告统计 ==")
        page.goto(BASE + "/report", wait_until="networkidle")
        page.get_by_role("button", name="统计").click()
        page.wait_for_timeout(800)
        check(page.locator(".heatmap").count() > 0, "热力图")
        check(page.locator("svg[aria-label='近14天学习量']").count() > 0, "折线图")
        shot(page, "08-report-stats")
        page.get_by_role("button", name="覆盖").click()
        page.wait_for_timeout(500)
        check(page.locator(".tree-subject").count() > 0, "覆盖树")
        shot(page, "09-coverage")

        # 8. 我的
        page.goto(BASE + "/settings", wait_until="networkidle")
        check(page.locator("h1", has_text="我的").count() > 0, "设置页")
        shot(page, "10-settings")

        browser.close()

    print("\n== 结果 ==")
    if errors:
        print(f"共 {len(errors)} 个问题：")
        for e in errors[:20]:
            print(" -", e)
        sys.exit(1)
    print("全部通过，截图见 frontend/e2e/shots/")


if __name__ == "__main__":
    main()
