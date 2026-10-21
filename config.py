import os

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Source group (jaha se forward karna hai)
SOURCE_CHAT_ID = int(os.environ.get("SOURCE_CHAT_ID", 0))

# Destination group
DEST_CHAT_ID = int(os.environ.get("DEST_CHAT_ID", 0))

# Destination topic ID (agar destination me topics enabled hai)
# Agar topic nahi hai to 0 rakho
DEST_TOPIC_ID = int(os.environ.get("DEST_TOPIC_ID", 0))

# Source me agar kisi specific topic se uthana hai (optional)
SOURCE_TOPIC_ID = int(os.environ.get("SOURCE_TOPIC_ID", 0))

# Owner user ID (commands control ke liye)
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# Delay between messages (seconds) - FloodWait avoid karne ke liye
FORWARD_DELAY = float(os.environ.get("FORWARD_DELAY", 0.3))

# Kitne messages tak jana hai (history limit) - 0 = unlimited
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", 0))
