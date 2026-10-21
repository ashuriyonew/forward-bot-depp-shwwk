import asyncio
import logging
import json
import os

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

CONFIG_FILE = "config_data.json"


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


CFG = load_config()
# Keys: source_chat, dest_chat, dest_topic, source_topic, delay

def cfg_get(key, default=None):
    return CFG.get(key, default)

def cfg_set(key, value):
    CFG[key] = value
    save_config(CFG)


app = Client(
    "forward_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    sleep_threshold=10,
)

STATE = {
    "running": False,
    "stop": False,
    "live": False,
    "forwarded": 0,
    "failed": 0,
}


def topic_kwargs(topic_id):
    if topic_id and int(topic_id) > 0:
        return {"reply_to_message_id": int(topic_id)}
    return {}


async def forward_single(client, message: Message) -> bool:
    dest_chat = cfg_get("dest_chat")
    dest_topic = cfg_get("dest_topic", 0)
    if not dest_chat:
        log.error("Destination chat not set!")
        return False
    try:
        await client.forward_messages(
            chat_id=int(dest_chat),
            from_chat_id=message.chat.id,
            message_ids=message.id,
            **topic_kwargs(dest_topic),
        )
        return True
    except FloodWait as e:
        log.warning(f"FloodWait {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await forward_single(client, message)
    except ChatForwardsRestricted:
        try:
            await client.copy_message(
                chat_id=int(dest_chat),
                from_chat_id=message.chat.id,
                message_id=message.id,
                **topic_kwargs(dest_topic),
            )
            return True
        except Exception as ce:
            log.error(f"Copy fallback failed {message.id}: {ce}")
            return False
    except MessageIdInvalid:
        log.error(f"Invalid msg {message.id}")
        return False
    except Exception as e:
        log.error(f"Forward failed {message.id}: {e}")
        return False


# ---------------- HELP ----------------
HELP_TEXT = """
**🤖 Advanced Forward Bot**

**Setup Commands (Owner only):**
• `/setsource <chat_id>` — Source group/channel
• `/setdest <chat_id>` — Destination group/channel
• `/setsrctopic <topic_id>` — Source topic (0 = none)
• `/setdesttopic <topic_id>` — Dest topic (0 = none)
• `/setdelay <seconds>` — Delay (default 0.5)
• `/config` — Current settings dekhne ke liye

**Action Commands:**
• `/forward` — History forward (source → dest)
• `/live` — Naye messages auto-forward ON
• `/liveoff` — Live mode OFF
• `/stop` — Sab stop
• `/status` — Stats

**Note:** Bot ko source me add karo aur dest me Admin (Post Messages) banao.
"""


@app.on_message(filters.command("start") & filters.user(OWNER_ID))
async def cmd_start(client, message: Message):
    await message.reply(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("help") & filters.user(OWNER_ID))
async def cmd_help(client, message: Message):
    await message.reply(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


# ---------------- SET COMMANDS ----------------
@app.on_message(filters.command("setsource") & filters.user(OWNER_ID))
async def cmd_setsource(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setsource -1001234567890`", parse_mode=ParseMode.MARKDOWN)
    try:
        chat_id = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid chat id (integer hona chahiye).")
    try:
        chat = await client.get_chat(chat_id)
        title = chat.title or chat.username or str(chat_id)
    except Exception as e:
        return await message.reply(f"❌ Chat access nahi mila: `{e}`\nBot ko us group me add karo pehle.", parse_mode=ParseMode.MARKDOWN)
    cfg_set("source_chat", chat_id)
    await message.reply(f"✅ Source set: **{title}**\n`{chat_id}`", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("setdest") & filters.user(OWNER_ID))
async def cmd_setdest(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setdest -1009876543210`", parse_mode=ParseMode.MARKDOWN)
    try:
        chat_id = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid chat id.")
    try:
        chat = await client.get_chat(chat_id)
        title = chat.title or chat.username or str(chat_id)
    except Exception as e:
        return await message.reply(f"❌ Chat access nahi mila: `{e}`\nBot ko dest group me Admin banao.", parse_mode=ParseMode.MARKDOWN)
    cfg_set("dest_chat", chat_id)
    await message.reply(f"✅ Destination set: **{title}**\n`{chat_id}`", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("setsrctopic") & filters.user(OWNER_ID))
async def cmd_setsrctopic(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setsrctopic 12` (0 = none)")
    try:
        tid = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid topic id.")
    cfg_set("source_topic", tid)
    await message.reply(f"✅ Source topic set: `{tid}`" + (" (none)" if tid == 0 else ""))


@app.on_message(filters.command("setdesttopic") & filters.user(OWNER_ID))
async def cmd_setdesttopic(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setdesttopic 45` (0 = none)")
    try:
        tid = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid topic id.")
    cfg_set("dest_topic", tid)
    await message.reply(f"✅ Dest topic set: `{tid}`" + (" (none)" if tid == 0 else ""))


@app.on_message(filters.command("setdelay") & filters.user(OWNER_ID))
async def cmd_setdelay(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setdelay 0.5`")
    try:
        d = float(args[1])
        if d < 0:
            raise ValueError
    except ValueError:
        return await message.reply("❌ Invalid delay value.")
    cfg_set("delay", d)
    await message.reply(f"✅ Delay set: `{d}s`")


@app.on_message(filters.command("config") & filters.user(OWNER_ID))
async def cmd_config(client, message: Message):
    text = (
        "**⚙️ Current Config**\n\n"
        f"Source: `{cfg_get('source_chat', 'Not set')}`\n"
        f"Dest: `{cfg_get('dest_chat', 'Not set')}`\n"
        f"Source Topic: `{cfg_get('source_topic', 0)}`\n"
        f"Dest Topic: `{cfg_get('dest_topic', 0)}`\n"
        f"Delay: `{cfg_get('delay', 0.5)}s`\n"
    )
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)


# ---------------- STATUS / STOP ----------------
@app.on_message(filters.command("status") & filters.user(OWNER_ID))
async def cmd_status(client, message: Message):
    await message.reply(
        f"**📊 Status**\n"
        f"History Running: `{STATE['running']}`\n"
        f"Live: `{STATE['live']}`\n"
        f"Forwarded: `{STATE['forwarded']}`\n"
        f"Failed: `{STATE['failed']}`"
    )


@app.on_message(filters.command("stop") & filters.user(OWNER_ID))
async def cmd_stop(client, message: Message):
    STATE["stop"] = True
    STATE["running"] = False
    STATE["live"] = False
    await message.reply("🛑 Sab stop ho gaya.")


# ---------------- HISTORY FORWARD ----------------
@app.on_message(filters.command("forward") & filters.user(OWNER_ID))
async def cmd_forward(client, message: Message):
    source = cfg_get("source_chat")
    dest = cfg_get("dest_chat")
    if not source or not dest:
        return await message.reply(
            "❌ Pehle `/setsource` aur `/setdest` karo.",
            parse_mode=ParseMode.MARKDOWN,
        )
    if STATE["running"]:
        return await message.reply("⚠️ Already running. Pehle `/stop` karo.")

    STATE["running"] = True
    STATE["stop"] = False
    STATE["forwarded"] = 0
    STATE["failed"] = 0

    await message.reply("🚀 History forward started...")

    delay = float(cfg_get("delay", 0.5))
    src_topic = int(cfg_get("source_topic", 0))

    try:
        count = 0
        async for msg in app.get_chat_history(int(source)):
            if STATE["stop"]:
                break

            if src_topic > 0:
                thread_id = getattr(msg, "message_thread_id", None) or \
                            (msg.reply_to_message.id if msg.reply_to_message else None)
                if thread_id != src_topic:
                    continue

            ok = await forward_single(app, msg)
            if ok:
                STATE["forwarded"] += 1
            else:
                STATE["failed"] += 1

            count += 1
            if count % 50 == 0:
                log.info(f"Processed {count} | OK={STATE['forwarded']} FAIL={STATE['failed']}")

            await asyncio.sleep(delay)

        await message.reply(
            f"✅ **Done**\nForwarded: `{STATE['forwarded']}`\nFailed: `{STATE['failed']}`"
        )
    except Exception as e:
        log.exception("History forward error")
        await message.reply(f"❌ Error: `{e}`")
    finally:
        STATE["running"] = False


# ---------------- LIVE MODE ----------------
@app.on_message(filters.command("live") & filters.user(OWNER_ID))
async def cmd_live_on(client, message: Message):
    if not cfg_get("source_chat") or not cfg_get("dest_chat"):
        return await message.reply("❌ Pehle source/dest set karo.")
    STATE["live"] = True
    await message.reply("🔴 Live mode ON — naye messages auto forward honge.")


@app.on_message(filters.command("liveoff") & filters.user(OWNER_ID))
async def cmd_live_off(client, message: Message):
    STATE["live"] = False
    await message.reply("⚪ Live mode OFF.")


# NOTE: filter.chat dynamic nahi hota, isliye generic handler use karenge
@app.on_message(filters.group | filters.channel, group=99)
async def live_forward(client, message: Message):
    if not STATE["live"]:
        return
    source = cfg_get("source_chat")
    if not source or message.chat.id != int(source):
        return
    if getattr(message, "service", None):
        return

    src_topic = int(cfg_get("source_topic", 0))
    if src_topic > 0:
        thread_id = getattr(message, "message_thread_id", None) or \
                    (message.reply_to_message.id if message.reply_to_message else None)
        if thread_id != src_topic:
            return

    ok = await forward_single(app, message)
    if ok:
        STATE["forwarded"] += 1
    else:
        STATE["failed"] += 1

    await asyncio.sleep(float(cfg_get("delay", 0.5)))


# ---------------- BOOT ----------------
log.info("Starting Advanced Forward Bot...")
app.run()
