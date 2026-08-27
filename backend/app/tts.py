"""edge-tts 合成与按条目缓存。

mp3 以条目 ID 命名存 AUDIO_DIR，已存在直接复用（导入/重排不重复合成）。
"""
import shutil
import subprocess
import sys
from pathlib import Path

from app import config

VOICE = "zh-CN-XiaoxiaoNeural"


def _edge_tts_bin() -> str:
    """优先取当前虚拟环境的 edge-tts 可执行文件，避免 PATH 不含 .venv/bin。"""
    exe = Path(sys.executable).parent / "edge-tts"
    if exe.exists():
        return str(exe)
    return shutil.which("edge-tts") or "edge-tts"


def ensure_mp3(entry_id: str, text: str, dry_run: bool = False) -> Path:
    out = config.AUDIO_DIR / f"{entry_id}.mp3"
    if out.exists() and out.stat().st_size > 0:
        return out
    if dry_run:
        return out
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [_edge_tts_bin(), "--voice", VOICE, "--text", text, "--write-media", str(out)],
            check=True,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001 - 合成失败不中断核心流程，由路由返回 503
        pass
    # 空文件不缓存：删除以便下次重试（否则 0 字节文件会永久短路）
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
    return out


def ensure_batch(items: list[tuple[str, str]], dry_run: bool = False) -> list[Path]:
    return [ensure_mp3(entry_id, text, dry_run) for entry_id, text in items]
