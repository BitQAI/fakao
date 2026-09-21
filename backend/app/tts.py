"""千问 TTS 合成（模型按序降级）与按条目缓存。

音频以条目 ID 命名（.wav）存 AUDIO_DIR，已存在且非空直接复用。
合成失败或无 key 时不落盘（删除空文件），由路由返回 503 供前端提示重试。
朗读前统一走 app.tts_text.normalize（确定性归一，见该模块注释）。
"""
import base64
import contextlib
import wave
import subprocess
import sys
from datetime import datetime
from hashlib import sha1
from pathlib import Path

import httpx

from app import config
from app.tts_text import normalize

TTS_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
TIMEOUT = 120.0


def _slow_down(content: bytes) -> bytes:
    """按 config.TTS_SPEED 用 ffmpeg atempo 变慢音频；失败时原样返回。"""
    try:
        speed = float(config.TTS_SPEED)
    except (TypeError, ValueError):
        return content
    speed = max(0.5, min(2.0, speed))
    if abs(speed - 1.0) < 1e-6:
        return content
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0",
             "-filter:a", f"atempo={speed:.6f}", "-f", "wav", "pipe:1"],
            input=content, capture_output=True, check=True, timeout=120,
        )
        return proc.stdout
    except Exception as exc:  # noqa: BLE001 - 变慢失败不阻断生成
        print(f"[tts] 变慢失败，按原速返回：{exc}", file=sys.stderr)
        return content


def _synthesize(text: str) -> bytes | None:
    """按 TTS_MODELS 顺序尝试各模型；主 key 全失败后回退备用 key。

    成功返回音频字节，全部失败返回 None。
    """
    keys = [k for k in (config.DASHSCOPE_API_KEY,
                        config.DASHSCOPE_API_KEY_FALLBACK) if k]
    if not keys:
        return None
    text = normalize(text)
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            for key in keys:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                for model in config.TTS_MODELS:
                    payload = {
                        "model": model,
                        "input": {"text": text, "voice": config.TTS_VOICE,
                                  "language_type": "Chinese"},
                    }
                    try:
                        resp = client.post(TTS_API_URL, json=payload, headers=headers)
                        resp.raise_for_status()
                        audio = (resp.json().get("output") or {}).get("audio") or {}
                        url = audio.get("url")
                        if url:
                            dl = client.get(url, timeout=TIMEOUT)
                            dl.raise_for_status()
                            return dl.content
                        b64 = audio.get("data")
                        if b64:
                            return base64.b64decode(b64)
                    except Exception:  # noqa: BLE001 - 该模型不可用则尝试下一个
                        continue
            return None
    except Exception:  # noqa: BLE001 - 网络/限流/解析失败一律返回 None
        return None


def ensure_mp3(entry_id: str, text: str, dry_run: bool = False,
               conn=None) -> Path:
    """对外接口名保持 ensure_mp3（路由/前端不感知），实际输出 .wav。

    传入 conn 时，本次真生成了新音频才写 tts_assets 台账（命中缓存不写库，
    保持快路径零写）。条目与法条题卡共用该路径。
    """
    out = config.AUDIO_DIR / f"{entry_id}.wav"
    if out.exists() and out.stat().st_size > 0:
        return out
    if dry_run:
        return out
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    content = render_audio(text)
    if content:
        out.write_bytes(content)
    # 空文件不缓存：删除以便下次重试（否则 0 字节文件会永久短路）
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
    elif conn is not None:
        record_asset(conn, entry_id, text, out)
    return out


def render_audio(text: str) -> bytes | None:
    """合成 + 变速，返回完整音频字节（不落盘）；失败返回 None。

    修复脚本用它做「先取新音频、成功再覆盖」，避免删除后合成失败导致条目失声。
    """
    content = _synthesize(text)
    if not content:
        return None
    return _slow_down(content)


def ensure_batch(items: list[tuple[str, str]], dry_run: bool = False) -> list[Path]:
    return [ensure_mp3(entry_id, text, dry_run) for entry_id, text in items]


# ---- 音频台账（audit/repair 用；合成主流程不依赖它） ----


def text_hash(text: str) -> str:
    """朗读文本（归一后）指纹：与音频一一对应。"""
    return sha1(normalize(text).encode("utf-8")).hexdigest()[:16]


def audio_duration_sec(path: Path) -> float:
    """读 wav 时长（秒）；非 wav / 损坏返回 0.0。"""
    try:
        with contextlib.closing(wave.open(str(path))) as w:
            return round(w.getnframes() / w.getframerate(), 3)
    except Exception:  # noqa: BLE001 - 坏文件按 0 处理，由审计脚本判定
        return 0.0


def chars_per_sec(text: str, duration_sec: float) -> float:
    """语速（字/秒）：0 表示无法判定。"""
    if duration_sec <= 0:
        return 0.0
    return round(len(normalize(text)) / duration_sec, 2)


def record_asset(conn, entry_id: str, text: str, path: Path) -> None:
    """写入/更新音频台账（幂等）。"""
    if not path.exists():
        return
    conn.execute(
        "INSERT INTO tts_assets (entry_id, text_hash, speed, bytes, duration_sec,"
        " created_at) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(entry_id) DO UPDATE SET text_hash=excluded.text_hash,"
        " speed=excluded.speed, bytes=excluded.bytes,"
        " duration_sec=excluded.duration_sec, created_at=excluded.created_at",
        (entry_id, text_hash(text), float(config.TTS_SPEED), path.stat().st_size,
         audio_duration_sec(path), datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
