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

# opencode zen 通道（deepseek-v4.1-flash，推理模型）：批量/离线生成优先用它
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "deepseek-v4.1-flash")
#: 该通道要求带 x-opencode-session 头（缺了会 400 MissingSessionID）
OPENCODE_SESSION = os.getenv("OPENCODE_SESSION", "fk-fakao-tool")
#: 推理模型先把预算花在思考上，给太小会返回空串，这里设下限
OPENCODE_MIN_MAX_TOKENS = int(os.getenv("OPENCODE_MIN_MAX_TOKENS", "1600"))
#: LLM 供应商顺序（只启用配置了 key 的；空串=不调用 LLM）
LLM_PROVIDER_ORDER = [p.strip() for p in os.getenv(
    "LLM_PROVIDER_ORDER", "opencode,deepseek").split(",") if p.strip()]
#: 交互式问答（流式）默认仍走 DeepSeek：opencode 是推理模型，首字延迟明显更高
LLM_CHAT_PROVIDER = os.getenv("LLM_CHAT_PROVIDER", "deepseek")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
# 备用 key：仅当主 key 的 TTS_MODELS 全部失败时启用（缺省为空=不启用）
DASHSCOPE_API_KEY_FALLBACK = os.getenv("DASHSCOPE_API_KEY_FALLBACK", "")
TTS_MODELS = [m.strip() for m in os.getenv(
    "TTS_MODELS",
    "qwen-tts,qwen-tts-2025-05-22,qwen-tts-2025-04-10",
).split(",") if m.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "Ethan")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))  # 语速倍数，1.0 正常，<1 变慢

DATA_DIR = Path(os.getenv("FAKAO_DATA_DIR", str(ROOT_DIR / "data")))
DB_PATH = DATA_DIR / "fakao.db"
AUDIO_DIR = DATA_DIR / "audio"
SOURCE_DIR = DATA_DIR  # 源材料树（data/），检索时按 ref 文件名递归匹配
STATUTE_DIR = DATA_DIR / "法条库"  # 法条全文库（只读，运行时解析）
CASES_DIR = DATA_DIR / "案例库统一"
CASES_DOCS_DIR = CASES_DIR / "documents"
CASES_INDEX = CASES_DIR / "index.csv"
