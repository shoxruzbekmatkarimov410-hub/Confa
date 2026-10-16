import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
_ch = os.environ["CHANNEL_ID"].strip()
CHANNEL_ID = _ch if _ch.startswith("@") else int(_ch)  # @username yoki -100... raqam
MOD_CHAT_ID = int(os.environ["MOD_CHAT_ID"])
OWNER_ID = int(os.environ["OWNER_ID"])
DATABASE_URL = os.environ["DATABASE_URL"]
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "60"))
BLOCK_LINKS = os.getenv("BLOCK_LINKS", "0") == "1"        # 1 = havolani avto-rad etish
BLOCK_USERNAMES = os.getenv("BLOCK_USERNAMES", "0") == "1"  # 1 = @username ni avto-rad etish
BLOCK_PHONES = os.getenv("BLOCK_PHONES", "1") == "1"        # 1 = telefon raqamni avto-rad etish
MAX_LEN = 900  # rasm/ovoz captioni 1024 bilan cheklangan
PERM_BAN = 4102444800  # 2100-yil
