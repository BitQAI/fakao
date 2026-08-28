"""路径与环境变量唯一入口。

.env 文件位于仓库根（backend/..），只保存密钥类配置。
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_PATH = ROOT_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ENV_PATH)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
TTS_MODELS = [m.strip() for m in os.getenv(
    "TTS_MODELS",
    "qwen-tts-latest,qwen-tts,qwen-tts-2025-05-22,qwen-tts-2025-04-10",
).split(",") if m.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "Ethan")

DATA_DIR = Path(os.getenv("FAKAO_DATA_DIR", str(ROOT_DIR / "data")))
DB_PATH = DATA_DIR / "fakao.db"
AUDIO_DIR = DATA_DIR / "audio"
SOURCE_DIR = DATA_DIR  # 源材料树（data/），检索时按 ref 文件名递归匹配
STATUTE_DIR = DATA_DIR / "法条库"  # 法条全文库（只读，运行时解析）
CASES_DIR = DATA_DIR / "案例库统一"
CASES_DOCS_DIR = CASES_DIR / "documents"
CASES_INDEX = CASES_DIR / "index.csv"
