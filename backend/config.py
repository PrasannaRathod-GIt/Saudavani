
import os
import re
from datetime import timedelta, timezone
from pathlib import Path
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(
    dotenv_path=Path(__file__).resolve().with_name(".env"),
    override=False,
)


# ---------------------------------------------------------------------------
# Gnani STT / TTS
# ---------------------------------------------------------------------------

GNANI_API_KEY = os.getenv("GNANI_API_KEY", "").strip()
GNANI_BASE_URL = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/")
GNANI_STT_URL = os.getenv("GNANI_STT_URL", f"{GNANI_BASE_URL}/stt/v3").strip()
GNANI_TTS_URL = os.getenv("GNANI_TTS_URL", f"{GNANI_BASE_URL}/api/v1/tts/inference").strip()
GNANI_STT_MODEL = os.getenv("GNANI_STT_MODEL", "prisma-v3.0").strip()
GNANI_STT_LANGUAGE = os.getenv("GNANI_STT_LANGUAGE", "mr-IN,hi-IN,en-IN").strip()
GNANI_STT_FORMAT = os.getenv("GNANI_STT_FORMAT", "transcribe").strip()

# The default Kaveri voice is compatible with Timbre v2.5.
GNANI_TTS_MODEL = os.getenv("GNANI_TTS_MODEL", "timbre-v2.5").strip() or "timbre-v2.5"
GNANI_TTS_VOICE = os.getenv("GNANI_TTS_VOICE", "Kaveri").strip()
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg").strip()


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()


# ---------------------------------------------------------------------------
# data.gov.in / AGMARKNET
# ---------------------------------------------------------------------------

VERIFIED_RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"
LEGACY_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"

DATA_GOV_IN_API_KEY = os.getenv("DATA_GOV_IN_API_KEY", "").strip()

DATA_GOV_RESOURCE_ID = (
    os.getenv("DATA_GOV_RESOURCE_ID", VERIFIED_RESOURCE_ID).strip()
    or VERIFIED_RESOURCE_ID
)

_RESOURCE_ID_OVERRIDDEN = DATA_GOV_RESOURCE_ID == LEGACY_RESOURCE_ID

if _RESOURCE_ID_OVERRIDDEN:
    DATA_GOV_RESOURCE_ID = VERIFIED_RESOURCE_ID

_env_api_url = os.getenv("DATA_GOV_API_URL", "").strip().split("?", 1)[0].rstrip("/")
_API_URL_IGNORED = bool(_env_api_url) and DATA_GOV_RESOURCE_ID not in _env_api_url

DATA_GOV_API_URL = (
    _env_api_url
    if (_env_api_url and not _API_URL_IGNORED)
    else f"https://api.data.gov.in/resource/{DATA_GOV_RESOURCE_ID}"
)

DATA_GOV_STATE = os.getenv("DATA_GOV_STATE", "Maharashtra").strip()
DATA_GOV_LIMIT = max(100, min(int(os.getenv("DATA_GOV_LIMIT", "1000")), 1000))
DATA_GOV_TIMEOUT = max(5, int(os.getenv("DATA_GOV_TIMEOUT_SECONDS", "30")))
DATA_GOV_TRANSPORT = os.getenv("DATA_GOV_TRANSPORT", "auto").strip().lower()
DATA_GOV_CURL_URL_IN_ARGS = (
    os.getenv("DATA_GOV_CURL_URL_IN_ARGS", "false").lower()
    in {"1", "true", "yes"}
)
DATA_GOV_MAX_ATTEMPTS = 6

PRICE_CACHE_SECONDS = max(60, int(os.getenv("PRICE_CACHE_SECONDS", "900")))
PRICE_STALE_HOURS = max(1, int(os.getenv("PRICE_STALE_HOURS", "72")))


# ---------------------------------------------------------------------------
# Database and demo settings
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("SAUDAVANI_DB_PATH", "saudavani.db")).resolve()

ADVANCE_PERCENT = max(
    0.0,
    min(float(os.getenv("DEMO_ADVANCE_PERCENT", "20")), 100.0),
)

DEMO_SINGLE_PARTY_LOCK = (
    os.getenv("DEMO_SINGLE_PARTY_LOCK", "false").lower()
    in {"1", "true", "yes"}
)

DEMO_ALLOW_UNAUTHENTICATED_ACTIONS = (
    os.getenv("DEMO_ALLOW_UNAUTHENTICATED_ACTIONS", "false").lower()
    in {"1", "true", "yes"}
)


# ---------------------------------------------------------------------------
# Application limits and constants
# ---------------------------------------------------------------------------

SESSION_HISTORY_LIMIT = 30
DEFAULT_OFFER_VALID_MINUTES = 30
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(15 * 1024 * 1024)))

DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
IST = timezone(timedelta(hours=5, minutes=30))
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
