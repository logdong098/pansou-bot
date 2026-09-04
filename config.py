import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Telegram Bot Token (from @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Proxy setting (e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:7890")
# Necessary in regions where Telegram is blocked
PROXY = os.getenv("PROXY", "").strip() or None

# Database path
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "pansou.db"))

# Default monitored public Telegram channels (channel usernames without @)
DEFAULT_CHANNELS = [
    "yunpanpan",           # 综合网盘 (夸克/阿里/百度)
    "ucpanpan",            # UC网盘/夸克网盘
    "yppshare",            # 夸克/阿里电影电视剧
    "hao1234cn",           # 综合资源
    "Quark_Share_Group",   # 夸克分享专区
    "alyp_4K_remux",       # 高清4K原盘影视
    "shareAliyun",         # 阿里云盘资源
]

raw_channels = os.getenv("CHANNELS", "")
if raw_channels.strip():
    MONITORED_CHANNELS = [c.strip().lstrip("@") for c in raw_channels.split(",") if c.strip()]
else:
    MONITORED_CHANNELS = DEFAULT_CHANNELS

# 网盘类型过滤：当前只采集/搜索夸克网盘
raw_pan_types = os.getenv("PAN_TYPES", "quark")
PAN_TYPES = [p.strip().lower() for p in raw_pan_types.split(",") if p.strip()]

# Crawl settings
CRAWL_PAGES_PER_CHANNEL = int(os.getenv("CRAWL_PAGES_PER_CHANNEL", "3"))
CRAWL_INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", "60"))

# Authorized admin user IDs (optional, for /crawl command)
admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(i.strip()) for i in admin_ids_str.split(",") if i.strip().isdigit()]
