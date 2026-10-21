import asyncio
import logging
import os
import re
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatForwardsRestricted, MessageIdInvalid
from pyrogram.enums import ParseMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("ForwardBot")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
PORT = int(os.environ.get("PORT", 10000))

# Temporary per-user memory (multi-step input)
USER_STATE = {}

app = Client(
    "forward_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    sleep_threshold=10,
)

# ---------------- DUMMY WEB SERVER (Render free plan ke liye) ----------------
class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - bot running")

    def log_message(self, *args):
        pass

def run_web():
    server = HTTPServer(("0.0.0.0", PORT), Ping)
    log.info(f"Dummy web server listening on {PORT}")
    server.serve_forever()


# ---------------- LINK PARSER ----------------
# Supported:
#   https://t.me/c/4421160772/715/724-792
#   https://t.me/c/4421160772/715
#   https://t.me/c/4421160772/715/724
#   https://t.me/c/4421160772/724-792
# Returns: (chat_id, topic_id, first_id, last_id)
def parse_link(link: str):
    # t.me/c/<internal_id>/[topic/]<first>[-<last>]
    m = re.match(
        r"https?://t\.me/c/(\d+)(?:/(\d+))?(?:/(\d+)(?:-(\d+))?)?",
        link.strip()
    )
    if not m:
        # private channel alt format
        m2 = re.match(
            r"https?://t\.me/([A-Za-z0-9_]+)(?:/(\d+))?(?:/(\d+)(?:-(\d+))?)?",
            link.strip()
        )
        if not m2:
            return None
        username = m2.group(1)
        topic = int(m2.group(2)) if m2.group(2) else 0
        first = int(m2.group(3)) if m2.group(3) else 1
        last = int(m2.group(4)) if m2.group(4) else first
        return (username, topic, first, last)

    internal = int(m.group(1))
    chat_id = int(f"-100{internal}")

    # Ambiguous: group(2) could be topic, group(3) could be msg or topic
    a = m.group(2)
    b = m.group(3)
    c = m.group(4)

    if b is None and c is None:
        # /c/ID/715  → 715 could be msg_id or topic
        # assume 715 is message id, no topic
        topic = 0
        first = int(a) if a else 1
        last = first
    elif c is None:
        # /c/ID/715/724  → topic=715, msg=724
        topic = int(a)
        first = int(b)
        last = int(b)
    else:
        # /c/ID/715/724-792  → topic=715, first=724, last=792
        topic = int(a)
        first = int(b)
        last = int(c)

    return (chat_id, topic, first, last)


# ---------------- CORE FORWARD ----------------
async def forward_one(chat_id, msg_id, dest_chat, dest_topic, retries=3):
    for attempt in range(retries):
        try:
            await app.forward_messages(
                chat_id=dest_chat,
                from_chat_id=chat_id,
                message_ids=msg_id,
                **({"reply_to_message_id": dest_topic} if dest_topic else {})
            )
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            continue
        except ChatForwardsRestricted:
            try:
                await app.copy_message(
                    chat_id=dest_chat,
                    from_chat_id=chat_id,
                    message_id=msg_id,
                    **({"reply_to_message_id": dest_topic} if dest_topic else {})
                )
                return True
            except Exception:
                return False
        except MessageIdInvalid:
            return False
        except Exception as e:
            log.error(f"fail {msg_id}: {e}")
            await asyncio.sleep(1)
    return False


# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start") & filters.user(OWNER_ID))
async def cmd_start(client, message: Message):
    await message.reply(
        "**🤖 Forward Bot**\n\n"
        "1️⃣ `/set <target_chat_id>` — dest group/channel ID\n"
        "2️⃣ `/forward <t.me link>` — source link\n\n"
        "**Link example:**\n"
        "`https://t.me/c/4421160772/715/724-792`\n\n"
        "Bot strictly `724` → `792` tak **sequence wise** forward karega.",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("set") & filters.user(OWNER_ID))
async def cmd_set(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/set -1001234567890`", parse_mode=ParseMode.MARKDOWN)
    try:
        cid = int(args[1])
        chat = await client.get_chat(cid)
    except Exception as e:
        return await message.reply(f"❌ `{e}`\nBot ko dest me Admin banao.", parse_mode=ParseMode.MARKDOWN)
    USER_STATE.setdefault(message.from_user.id, {})["dest"] = cid
    USER_STATE[message.from_user.id]["dest_topic"] = 0
    await message.reply(f"✅ Target set: **{chat.title or cid}**\n`{cid}`", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("settopic") & filters.user(OWNER_ID))
async def cmd_settopic(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/settopic 45` (0 = none)")
    try:
        tid = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid topic id.")
    USER_STATE.setdefault(message.from_user.id, {})["dest_topic"] = tid
    await message.reply(f"✅ Dest topic: `{tid}`")


@app.on_message(filters.command("forward") & filters.user(OWNER_ID))
async def cmd_forward(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply(
            "Usage: `/forward https://t.me/c/4421160772/715/724-792`",
            parse_mode=ParseMode.MARKDOWN,
        )

    user_state = USER_STATE.get(message.from_user.id, {})
    dest_chat = user_state.get("dest")
    dest_topic = user_state.get("dest_topic", 0)

    if not dest_chat:
        return await message.reply("❌ Pehle `/set <target_id>` karo.", parse_mode=ParseMode.MARKDOWN)

    parsed = parse_link(args[1].strip())
    if not parsed:
        return await message.reply("❌ Invalid link format.")

    chat_id, topic, first_id, last_id = parsed

    if last_id < first_id:
        return await message.reply("❌ Last ID < First ID. Check link.")

    status = await message.reply(
        f"🚀 **Started**\n"
        f"Source: `{chat_id}`" + (f" (topic `{topic}`)" if topic else "") + "\n"
        f"Range: `{first_id}` → `{last_id}`\n"
        f"Total: `{last_id - first_id + 1}`\n"
        f"Dest: `{dest_chat}`" + (f" (topic `{dest_topic}`)" if dest_topic else ""),
        parse_mode=ParseMode.MARKDOWN,
    )

    ok = fail = skipped = 0
    last_update = 0
    processed = 0

    # STRICT SEQUENCE: first → last
    for msg_id in range(first_id, last_id + 1):
        success = await forward_one(chat_id, msg_id, dest_chat, dest_topic)
        if success:
            ok += 1
        else:
            skipped += 1
        processed += 1

        if processed - last_update >= 20:
            last_update = processed
            try:
                await status.edit_text(
                    f"🚀 Running...\n"
                    f"`{processed}/{last_id - first_id + 1}`\n"
                    f"✅ {ok}  ⏭ {skipped}"
                )
            except Exception:
                pass

        await asyncio.sleep(0.3)

    await status.edit_text(
        f"✅ **Done**\n"
        f"Range: `{first_id}` → `{last_id}`\n"
        f"✅ Forwarded: `{ok}`\n"
        f"⏭ Skipped: `{skipped}`"
    )


@app.on_message(filters.command("status") & filters.user(OWNER_ID))
async def cmd_status(client, message: Message):
    u = USER_STATE.get(message.from_user.id, {})
    await message.reply(
        f"**⚙️ Settings**\n"
        f"Target: `{u.get('dest', 'Not set')}`\n"
        f"Dest topic: `{u.get('dest_topic', 0)}`"
    )


# ---------------- START ----------------
if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    log.info("Starting bot...")
    app.run()
