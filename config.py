# ═══════════════════════════════════════════════════
#  ⚙️  إعدادات المصنع
#  على Railway: حط القيم في Variables (مش هنا)
#  محلياً: تقدر تحط ملف .env أو تعدّل الـ defaults تحت
# ═══════════════════════════════════════════════════
import os

# ─── قراءة .env محلياً (اختياري) ────────────────────
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _get_env(name: str, default: str = "", required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"❌ متغير البيئة المطلوب غير موجود: {name}")
    return val


# ─── التوكن والمطور ────────────────────────────────
# توكن البوت الرئيسي (المصنع) — من @BotFather
FACTORY_TOKEN = _get_env(
    "BOT_TOKEN",
    default="8074615898:AAFAtxvRk8rPMezbH3kT0o939Snks3TUjSE",
    required=True,
)

# Telegram User ID بتاع المطور
ADMIN_USER_ID = int(_get_env("DEVELOPER_ID", default="1923931101"))

# 🎞️ جرافيك رسالة /start
START_GIF = _get_env(
    "START_GIF",
    default="https://i.postimg.cc/wxV3PspQ/1756574872401.gif",
)

# ─── مسارات التخزين ────────────────────────────────
# على Railway اربط Volume على /data علشان البيانات متضيعش مع كل deploy
# وحط الـ env variable: DATA_DIR=/data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = _get_env("DATA_DIR", default=os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
FORCE_SUB_FILE = os.path.join(DATA_DIR, "force_sub.json")
CHANNELS_DIR = os.path.join(DATA_DIR, "channels")

# ─── إعدادات الريأكشن ──────────────────────────────
REACTION_DELAY_MIN = int(_get_env("REACTION_DELAY_MIN", default="2"))
REACTION_DELAY_MAX = int(_get_env("REACTION_DELAY_MAX", default="8"))

# قنوات Premium يدوية (اختياري)
MANUAL_PREMIUM: list[str] = []
