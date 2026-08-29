"""千问 TTS 合成（模型按序降级）与按条目缓存。

音频以条目 ID 命名（.wav）存 AUDIO_DIR，已存在且非空直接复用。
合成失败或无 key 时不落盘（删除空文件），由路由返回 503 供前端提示重试。
"""
import base64
import subprocess
import sys
from pathlib import Path

import httpx

from app import config

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
    """按 TTS_MODELS 顺序尝试各模型，成功返回音频字节，全失败返回 None。"""
    if not config.DASHSCOPE_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
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


def ensure_mp3(entry_id: str, text: str, dry_run: bool = False) -> Path:
    """对外接口名保持 ensure_mp3（路由/前端不感知），实际输出 .wav。"""
    out = config.AUDIO_DIR / f"{entry_id}.wav"
    if out.exists() and out.stat().st_size > 0:
        return out
    if dry_run:
        return out
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    content = _synthesize(text)
    if content:
        content = _slow_down(content)
        out.write_bytes(content)
    # 空文件不缓存：删除以便下次重试（否则 0 字节文件会永久短路）
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
    return out


def ensure_batch(items: list[tuple[str, str]], dry_run: bool = False) -> list[Path]:
    return [ensure_mp3(entry_id, text, dry_run) for entry_id, text in items]
