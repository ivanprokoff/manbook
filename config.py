import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL", None)

MIN_VOTES = int(os.getenv("MIN_VOTES", "3"))

TIER_BOUNDARIES = {
    "S": 9.0,
    "A": 7.5,
    "B": 6.0,
    "C": 4.5,
    "D": 3.0,
    "F": 0.0,
}

ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", None)
if ALLOWED_CHAT_ID:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID)

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db")


ACCESS_MODE = os.getenv("ACCESS_MODE", "open")

_allowed_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: set[int] = set()
if _allowed_raw.strip():
    ALLOWED_USERS = {int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip()}

ADMIN_ID = os.getenv("ADMIN_ID", None)
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)