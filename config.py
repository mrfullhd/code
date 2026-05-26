import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "3"))
FREE_MAX_HEIGHT = int(os.getenv("FREE_MAX_HEIGHT", "720"))
FREE_MAX_FILE_MB = int(os.getenv("FREE_MAX_FILE_MB", "50"))
VIP_MAX_FILE_MB = int(os.getenv("VIP_MAX_FILE_MB", "2000"))

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
DATABASE_PATH = os.getenv("DATABASE_PATH", "./bot.db")
PROXY_URL = os.getenv("PROXY_URL", None)
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", None)
VIP_CONTACT = os.getenv("VIP_CONTACT", "@admin")

AUDIO_OPTIONS = [
    {"label": "MP3 192kbps", "format": "mp3", "quality": "192", "vip_only": False},
    {"label": "MP3 320kbps", "format": "mp3", "quality": "320", "vip_only": True},
    {"label": "M4A Best",    "format": "m4a", "quality": "best","vip_only": False},
]

MESSAGES = {
    "welcome": (
        "salam <b>{name}</b>!\n\n"
        "linkvideorobefarst.\n\n"
        "YouTube, Instagram, TikTok, Twitter, Vimeo, +1000 site\n\n"
        "hesab: {status}"
    ),
    "help": (
        "<b>rahnamaestfade</b>\n\n"
        "1 link befarst\n"
        "2 keyfiat entekhab kon\n"
        "3 sabr kon\n\n"
        "/start /status /vip /cancel\n\n"
        "Free: 3 download/roz ta 720p\n"
        "VIP: namahhdood ta 4K ta 2GB"
    ),
    "vip_info": (
        "<b>VIP Premium</b>\n\n"
        "download namahhdood\n"
        "keyfiat ta 4K\n"
        "fayl ta 2GB\n"
        "MP3 320kbps\n\n"
        "baraye kharid: {contact}"
    ),
    "not_vip": "ین کیفیت برای VIP هست!\n\n/vip",
    "daily_limit": "سقف روزانه پر شد!\n\n/vip",
    "extracting": "در حال استخراج اطلاعات...",
    "error_live": "ویدیوهای Live قابل دانلود نیستند.",
    "no_formats": "هیچ فرمتی پیدا نشد.",
    "cancelled": "لغو شد.",
    "select_quality": "<b>{title}</b>\n{duration} | {views}\n\nکیفیت انتخاب کنید:",
    "error_size": "فایل بزرگه! {size} > {max_size}\n\n/vip",
}
