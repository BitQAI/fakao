"""案例阅读记录（看过标记 + 阅读历史）测试。"""
import pytest

from app import case_views, db


@pytest.fixture()
def conn(tmp_db):
    db_path, _ = tmp_db
    c = db.connect(db_path)
    c.executemany(
        "INSERT INTO cases (source, loc, title, category, case_no, keywords, date, "
        "url, text) VALUES (?,?,?,?,?,?,?,?,?)",
        [("人民法院案例库", "case_1", "甲案", "参考案例", "", "[]", "2019.01.01", "",
          "正文一。"),
         ("人民法院案例库", "case_2", "乙案", "参考案例", "", "[]", "2020.01.01", "",
          "正文二。")])
    c.commit()
    return c


def test_mark_viewed_then_repeat(conn):
    first = case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    assert first["views"] == 1 and first["first_time"] is True
    again = case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    assert again["views"] == 2 and again["first_time"] is False
    assert again["first_viewed_at"] == first["first_viewed_at"]
    assert again["last_viewed_at"] >= first["last_viewed_at"]
    assert case_views.is_viewed(conn, "人民法院案例库", "case_1")
    assert not case_views.is_viewed(conn, "人民法院案例库", "case_2")


def test_viewed_keys(conn):
    assert case_views.viewed_keys(conn) == set()
    case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    assert case_views.viewed_keys(conn) == {("人民法院案例库", "case_1")}


def test_history_order_and_join(conn):
    case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    case_views.mark_viewed(conn, "人民法院案例库", "case_2")
    # 打点时间手工隔开，验证历史严格按「最近打开」倒序
    conn.execute("UPDATE case_views SET last_viewed_at='2026-09-22T10:00:00.000' "
                 "WHERE loc='case_1'")
    conn.execute("UPDATE case_views SET last_viewed_at='2026-09-22T11:00:00.000' "
                 "WHERE loc='case_2'")
    conn.commit()
    out = case_views.history(conn, limit=10)
    assert out["total"] == 2
    assert [i["loc"] for i in out["items"]] == ["case_2", "case_1"]
    assert out["items"][0]["title"] == "乙案"  # 标题 JOIN cases 取，不冗余存
    assert out["items"][0]["views"] == 1


def test_history_skips_records_missing_from_cases(conn):
    """案例库重装后悬空记录不展示、不报错。"""
    case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    case_views.mark_viewed(conn, "人民法院案例库", "case_gone")
    out = case_views.history(conn)
    assert out["total"] == 1 and [i["loc"] for i in out["items"]] == ["case_1"]


def test_clear(conn):
    case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    case_views.mark_viewed(conn, "人民法院案例库", "case_2")
    assert case_views.clear(conn) == 2
    assert case_views.viewed_keys(conn) == set()
    assert case_views.clear(conn) == 0
