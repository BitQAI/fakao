"""听学池自动续批：剩余可听条目低于阈值时，后台生成下一科目并合成音频。"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app import config, db, importer, tts  # noqa: E402
import generate_entries as gen  # noqa: E402

SUBJECT_ORDER = ["民诉", "商经知", "理论法", "三国法", "刑法", "民法", "行政法"]
SUBJECT_TARGET = 150
SUBJECT_PREFIX = gen.SUBJECT_PREFIX

_lock = threading.Lock()
_running = False


def next_pending_subject(conn) -> str | None:
    """按科目优先级返回 final 条数未达标的第一个科目。"""
    counts = {r["subject"]: r["n"] for r in conn.execute(
        "SELECT subject, COUNT(*) AS n FROM entries WHERE status='final' "
        "GROUP BY subject")}
    for s in SUBJECT_ORDER:
        if counts.get(s, 0) < SUBJECT_TARGET:
            return s
    return None


def _import_and_synth(subject: str) -> None:
    path = config.DATA_DIR / "entries" / f"{subject}.json"
    conn = db.connect()
    try:
        result = importer.import_file(conn, path)
        if result["errors"]:
            print(f"[generator] {subject} 导入失败: {result['errors'][:3]}")
            return
        conn.execute("UPDATE entries SET status='final' WHERE subject=?", (subject,))
        conn.commit()
    finally:
        conn.close()
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, tts_text FROM entries WHERE subject=? AND status='final' "
            "AND tts_text != ''", (subject,)).fetchall()
    finally:
        conn.close()
    for r in rows:
        tts.ensure_mp3(r["id"], r["tts_text"])
    print(f"[generator] {subject} 完成：导入并合成 {len(rows)} 条")


def _worker(subject: str) -> None:
    global _running
    try:
        stats = gen.generate(subject, target=SUBJECT_TARGET)
        print(f"[generator] {subject} 生成统计: {stats}")
        _import_and_synth(subject)
    except Exception as exc:  # noqa: BLE001
        print(f"[generator] {subject} 失败: {exc}")
    finally:
        _running = False


def ensure_generation(conn) -> bool:
    """池子不足且未在生成时，启动后台生成；返回是否触发。"""
    global _running
    subject = next_pending_subject(conn)
    if subject is None:
        return False
    with _lock:
        if _running:
            return False
        _running = True
    threading.Thread(target=_worker, args=(subject,), daemon=True).start()
    return True
