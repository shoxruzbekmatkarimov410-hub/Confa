import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
MOD_CHAT_ID = int(os.environ["MOD_CHAT_ID"])
OWNER_ID = int(os.environ["OWNER_ID"])
DATABASE_URL = os.environ["DATABASE_URL"]
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "60"))
MAX_LEN = 900  # rasm/ovoz captioni 1024 bilan cheklangan
PERM_BAN = 4102444800  # 2100-yil
