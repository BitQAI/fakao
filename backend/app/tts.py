"""edge-tts 合成与按条目缓存。

mp3 以条目 ID 命名存 AUDIO_DIR，已存在直接复用（导入/重排不重复合成）。
"""
import subprocess
from pathlib import Path

from app import config

VOICE = "zh-CN-XiaoxiaoNeural"


def ensure_mp3(entry_id: str, text: str, dry_run: bool = False) -> Path:
    out = config.AUDIO_DIR / f"{entry_id}.mp3"
    if out.exists() or dry_run:
        return out
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["edge-tts", "--voice", VOICE, "--text", text, "--write-media", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def ensure_batch(items: list[tuple[str, str]], dry_run: bool = False) -> list[Path]:
    return [ensure_mp3(entry_id, text, dry_run) for entry_id, text in items]
