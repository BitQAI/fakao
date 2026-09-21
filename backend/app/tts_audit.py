"""听学音频质检：判定坏录音与陈旧录音。

判定口径（2026-09-20 以 2426 条实测定标，中位语速 4.81 字/秒）：

| 类型 | 口径 | 处置 |
|---|---|---|
| missing | 有条目、无 wav | 重新合成 |
| empty | wav 为 0 字节 | 重新合成 |
| stale | 台账 hash ≠ 当前归一文本 hash | 重新合成 |
| suspect | 语速 <3.0 或 >6.5 字/秒（实测 >6.5 为截断） | 重新合成并比对 |
| untracked | wav 存在但台账无记录（历史文件） | 建档（不重合成） |

wave 级指标（整体 RMS、首尾静音）需要读全部音频，默认只在 audit 时计算。
"""
import array
import contextlib
import warnings
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app import config, tts
from app.tts_text import normalize

try:  # 纯标准库的 C 实现，比逐样本 Python 循环快两个数量级
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop
except ImportError:  # pragma: no cover - Python 3.13+ 已移除 audioop
    audioop = None

MIN_RATE = 3.0
MAX_RATE = 6.5
SILENCE_RMS = 40.0        # 单窗口低于该值视为静音
SILENCE_WINDOW_MS = 50
MAX_EDGE_SILENCE_SEC = 2.0
SILENT_OVERALL_RMS = 60.0

#: 默认「需重合成」的坏录音类型（条目口径：缺失音频本身就是故障）
DEFAULT_REPAIR_KINDS = ("missing", "empty", "stale", "suspect")
#: 法条题卡口径：missing 是「还没生成」的正常状态，不驱动批量重合成
CARD_REPAIR_KINDS = ("empty", "stale", "suspect", "over_length")
#: 听学单条卡片音频上限（用户口径：30 秒内）
MAX_CARD_DURATION_SEC = 30.0


@dataclass
class Issue:
    entry_id: str
    kind: str
    detail: str = ""
    chars: int = 0
    duration_sec: float = 0.0
    chars_per_sec: float = 0.0
    rms: float = 0.0
    lead_silence_sec: float = 0.0
    tail_silence_sec: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def wav_metrics(path: Path) -> dict:
    """一次性读出时长、整体 RMS、首尾静音时长（非 wav / 损坏返回 0 值）。"""
    out = {"duration_sec": 0.0, "rms": 0.0,
           "lead_silence_sec": 0.0, "tail_silence_sec": 0.0}
    try:
        with contextlib.closing(wave.open(str(path))) as w:
            rate = w.getframerate() or 24000
            frames = w.readframes(w.getnframes())
    except Exception:  # noqa: BLE001 - 坏文件交给调用方按 0 处理
        return out
    frames = frames[: len(frames) // 2 * 2]
    if not frames:
        return out
    total = len(frames) // 2
    out["duration_sec"] = round(total / rate, 3)
    out["rms"] = round(_rms(frames) or 0.0, 1)
    win_bytes = max(2, int(rate * SILENCE_WINDOW_MS / 1000) * 2)

    def window_rms(offset: int) -> float:
        return _rms(frames[offset:offset + win_bytes]) or 0.0

    lead = tail = 0
    i = 0
    while i + win_bytes <= len(frames) and window_rms(i) < SILENCE_RMS:
        i += win_bytes
    lead = i
    j = len(frames)
    while j - win_bytes >= 0 and window_rms(j - win_bytes) < SILENCE_RMS:
        j -= win_bytes
    tail = len(frames) - j
    lead, tail = round(lead / 2 / rate, 2), round(tail / 2 / rate, 2)
    out["lead_silence_sec"] = lead
    out["tail_silence_sec"] = tail
    return out


def _rms(frames: bytes) -> float:
    """16bit 小端 PCM 的 RMS；优先用 audioop（C 实现），否则退回纯 Python。"""
    if not frames:
        return 0.0
    if audioop is not None:
        return audioop.rms(frames, 2)
    samples = array.array("h")
    samples.frombytes(frames)
    return (sum(x * x for x in samples) / len(samples)) ** 0.5


def audit_entry(conn, entry_id: str, text: str, *, wave_metrics: bool = True,
                manifest: dict | None = None,
                max_duration_sec: float = 0.0) -> list[Issue]:
    """单条目质检，返回 0~n 条 Issue。max_duration_sec>0 时超时记 over_length。"""
    path = config.AUDIO_DIR / f"{entry_id}.wav"
    normalized = normalize(text)
    issues: list[Issue] = []
    base = {"chars": len(normalized)}
    if not path.exists():
        return [Issue(entry_id=entry_id, kind="missing", detail="无 wav", **base)]
    if path.stat().st_size == 0:
        return [Issue(entry_id=entry_id, kind="empty", detail="0 字节", **base)]

    row = (manifest or {}).get(entry_id)
    if row is None:
        issues.append(Issue(entry_id=entry_id, kind="untracked",
                            detail="台账无记录", **base))
    elif row["text_hash"] != tts.text_hash(text):
        issues.append(Issue(entry_id=entry_id, kind="stale",
                            detail="文本已改，音频早于文本", **base))

    metrics = wav_metrics(path) if wave_metrics else {
        "duration_sec": tts.audio_duration_sec(path), "rms": 0.0,
        "lead_silence_sec": 0.0, "tail_silence_sec": 0.0}
    rate = tts.chars_per_sec(text, metrics["duration_sec"])
    fields = {k: metrics[k] for k in ("duration_sec", "rms", "lead_silence_sec",
                                      "tail_silence_sec")}
    if max_duration_sec and metrics["duration_sec"] > max_duration_sec:
        issues.append(Issue(
            entry_id=entry_id, kind="over_length",
            detail=f"超时长 {metrics['duration_sec']}s > {max_duration_sec}s",
            chars_per_sec=rate, **base, **fields))
    if metrics["duration_sec"] > 0 and not MIN_RATE <= rate <= MAX_RATE:
        issues.append(Issue(entry_id=entry_id, kind="suspect",
                            detail=f"语速异常 {rate} 字/秒", chars_per_sec=rate,
                            **base, **fields))
    if wave_metrics:
        if metrics["rms"] < SILENT_OVERALL_RMS:
            issues.append(Issue(entry_id=entry_id, kind="suspect",
                                detail=f"整体近乎无声 RMS={metrics['rms']}",
                                chars_per_sec=rate, **base, **fields))
        elif max(metrics["lead_silence_sec"],
                 metrics["tail_silence_sec"]) > MAX_EDGE_SILENCE_SEC:
            issues.append(Issue(
                entry_id=entry_id, kind="suspect",
                detail=f"首/尾静音过长 {metrics['lead_silence_sec']}/"
                       f"{metrics['tail_silence_sec']} 秒",
                chars_per_sec=rate, **base, **fields))
    return issues


def load_manifest(conn) -> dict:
    return {r["entry_id"]: {"text_hash": r["text_hash"], "bytes": r["bytes"],
                            "duration_sec": r["duration_sec"]}
            for r in conn.execute("SELECT * FROM tts_assets")}


def audit_entries(conn, rows, *, wave_metrics: bool = True,
                  limit: int = 0, max_duration_sec: float = 0.0) -> list[Issue]:
    """批量质检。rows 为 [{id, tts_text}, ...]。"""
    manifest = load_manifest(conn)
    issues: list[Issue] = []
    for i, r in enumerate(rows, 1):
        issues += audit_entry(conn, r["id"], r["tts_text"] or "",
                              wave_metrics=wave_metrics, manifest=manifest,
                              max_duration_sec=max_duration_sec)
        if limit and i >= limit:
            break
    return issues


def summarize(issues: list[Issue],
              repair_kinds: tuple[str, ...] = DEFAULT_REPAIR_KINDS) -> dict:
    """按类型汇总，并给出可直接驱动 repair 的 id 清单。

    repair_kinds 决定哪些类型算「需重合成」：条目含 missing，法条题卡不含
    （卡片音频按需生成，缺失属待生成）。
    """
    by_kind: dict[str, list[str]] = {}
    for issue in issues:
        by_kind.setdefault(issue.kind, []).append(issue.entry_id)
    repair = sorted({i for k in repair_kinds
                     for i in by_kind.get(k, [])})
    return {
        "counts": {k: len(v) for k, v in sorted(by_kind.items())},
        "ids": by_kind,
        "repair_ids": repair,
    }
