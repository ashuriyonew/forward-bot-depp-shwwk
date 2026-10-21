import asyncio
import logging
import json
import os
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait, ChatForwardsRestricted, MessageIdInvalid,
    ChannelInvalid, ChatWriteForbidden,
)
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

# ---------------- CONFIG PERSISTENCE ----------------
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

CFG = load_config()

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
    workers=100,
    sleep_threshold=10,
)

# ---------------- STATE ----------------
STATE = {
    "running": False,
    "stop": False,
    "live": False,
    "forwarded": 0,
    "failed": 0,
    "skipped": 0,
    "total": 0,
    "current_id": 0,
    "status_msg_id": None,
    "status_chat_id": None,
}


def topic_kwargs(topic_id):
    try:
        tid = int(topic_id or 0)
    except Exception:
        tid = 0
    return {"reply_to_message_id": tid} if tid > 0 else {}


# ---------------- CORE FORWARD ----------------
async def forward_single(client, chat_id, message_id, retries=3) -> bool:
    """Ek single message forward. FloodWait / restricted handle."""
    dest_chat = cfg_get("dest_chat")
    dest_topic = cfg_get("dest_topic", 0)
    if not dest_chat:
        return False

    for attempt in range(retries):
        try:
            await client.forward_messages(
                chat_id=int(dest_chat),
                from_chat_id=int(chat_id),
                message_ids=message_id,
                **topic_kwargs(dest_topic),
            )
            return True
        except FloodWait as e:
            wait = e.value + 2
            log.warning(f"FloodWait {wait}s — sleeping")
            await asyncio.sleep(wait)
            continue
        except ChatForwardsRestricted:
            # fallback copy
            try:
                await client.copy_message(
                    chat_id=int(dest_chat),
                    from_chat_id=int(chat_id),
                    message_id=message_id,
                    **topic_kwargs(dest_topic),
                )
                return True
            except Exception as ce:
                log.error(f"Copy fallback fail {message_id}: {ce}")
                return False
        except (MessageIdInvalid, ChannelInvalid):
            log.warning(f"Msg {message_id} invalid/deleted — skip")
            return False
        except ChatWriteForbidden:
            log.error("Dest me post permission nahi — Admin banao.")
            return False
        except Exception as e:
            log.error(f"Forward fail {message_id} attempt {attempt+1}: {e}")
            await asyncio.sleep(1.5)
    return False


async def update_status(text: str):
    sid = STATE.get("status_msg_id")
    cid = STATE.get("status_chat_id")
    if sid and cid:
        try:
            await app.edit_message_text(cid, sid, text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass


# ---------------- HELP ----------------
HELP_TEXT = """
**🤖 Advanced Range Forward Bot**

**Setup:**
• `/setsource <chat_id>` — source group/channel
• `/setdest <chat_id>` — destination
• `/setsrctopic <id>` — source topic (0 = none)
• `/setdesttopic <id>` — dest topic (0 = none)
• `/setdelay <sec>` — delay (default 0.5)
• `/config` — settings dekho

**Range Forward (main feature):**
• `/forward <first_id> <last_id>` — first se last tak **sequence wise har single message**
  Example: `/forward 100 500`

**Live mode:**
• `/live` — naya message aate hi forward
• `/liveoff`
• `/stop` — sab stop
• `/status`

**Note:** Range forward me message ID order strictly maintain hoga (100 → 500). Delete hue IDs skip honge automatically.
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
        chat = await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ `{e}`\nPehle bot ko us chat me add karo.", parse_mode=ParseMode.MARKDOWN)
    cfg_set("source_chat", chat_id)
    await message.reply(f"✅ Source: **{chat.title or chat_id}**\n`{chat_id}`", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("setdest") & filters.user(OWNER_ID))
async def cmd_setdest(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setdest -1009876543210`", parse_mode=ParseMode.MARKDOWN)
    try:
        chat_id = int(args[1])
        chat = await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ `{e}`\nBot ko dest me Admin banao.", parse_mode=ParseMode.MARKDOWN)
    cfg_set("dest_chat", chat_id)
    await message.reply(f"✅ Dest: **{chat.title or chat_id}**\n`{chat_id}`", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("setsrctopic") & filters.user(OWNER_ID))
async def cmd_setsrctopic(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setsrctopic 12` (0=none)")
    try:
        tid = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid topic id.")
    cfg_set("source_topic", tid)
    await message.reply(f"✅ Source topic: `{tid}`")


@app.on_message(filters.command("setdesttopic") & filters.user(OWNER_ID))
async def cmd_setdesttopic(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/setdesttopic 45` (0=none)")
    try:
        tid = int(args[1])
    except ValueError:
        return await message.reply("❌ Invalid topic id.")
    cfg_set("dest_topic", tid)
    await message.reply(f"✅ Dest topic: `{tid}`")


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
        return await message.reply("❌ Invalid delay.")
    cfg_set("delay", d)
    await message.reply(f"✅ Delay: `{d}s`")


@app.on_message(filters.command("config") & filters.user(OWNER_ID))
async def cmd_config(client, message: Message):
    await message.reply(
        "**⚙️ Config**\n\n"
        f"Source: `{cfg_get('source_chat', 'Not set')}`\n"
        f"Dest: `{cfg_get('dest_chat', 'Not set')}`\n"
        f"Source Topic: `{cfg_get('source_topic', 0)}`\n"
        f"Dest Topic: `{cfg_get('dest_topic', 0)}`\n"
        f"Delay: `{cfg_get('delay', 0.5)}s`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------- STATUS / STOP ----------------
@app.on_message(filters.command("status") & filters.user(OWNER_ID))
async def cmd_status(client, message: Message):
    await message.reply(
        f"**📊 Status**\n"
        f"Running: `{STATE['running']}`\n"
        f"Live: `{STATE['live']}`\n"
        f"Current ID: `{STATE['current_id']}`\n"
        f"Forwarded: `{STATE['forwarded']}`\n"
        f"Failed: `{STATE['failed']}`\n"
        f"Skipped: `{STATE['skipped']}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("stop") & filters.user(OWNER_ID))
async def cmd_stop(client, message: Message):
    STATE["stop"] = True
    STATE["running"] = False
    STATE["live"] = False
    await message.reply("🛑 Stopped.")


# ---------------- MAIN: RANGE FORWARD ----------------
@app.on_message(filters.command("forward") & filters.user(OWNER_ID))
async def cmd_forward_range(client, message: Message):
    """
    /forward <first_id> <last_id>
    Strict sequence: first → last. Har single message.
    """
    args = message.text.split()
    if len(args) != 3:
        return await message.reply(
            "**Usage:** `/forward <first_msg_id> <last_msg_id>`\n"
            "Example: `/forward 100 500`",
            parse_mode=ParseMode.MARKDOWN,
        )

    try:
        first_id = int(args[1])
        last_id = int(args[2])
    except ValueError:
        return await message.reply("❌ IDs integer hone chahiye.")

    if first_id <= 0 or last_id <= 0 or last_id < first_id:
        return await message.reply("❌ Invalid range. Ensure: `first_id < last_id` both > 0.")

    source_chat = cfg_get("source_chat")
    dest_chat = cfg_get("dest_chat")
    if not source_chat or not dest_chat:
        return await message.reply("❌ Pehle `/setsource` aur `/setdest` karo.", parse_mode=ParseMode.MARKDOWN)

    if STATE["running"]:
        return await message.reply("⚠️ Already running. `/stop` karo pehle.")

    # init state
    STATE.update({
        "running": True,
        "stop": False,
        "forwarded": 0,
        "failed": 0,
        "skipped": 0,
        "total": last_id - first_id + 1,
        "current_id": first_id,
        "status_chat_id": message.chat.id,
    })

    status = await message.reply(
        f"🚀 **Range Forward Started**\n"
        f"Range: `{first_id}` → `{last_id}`\n"
        f"Total: `{STATE['total']}` messages\n"
        f"Sequence: strict\n\n"
        f"`Progress: 0/{STATE['total']}`",
        parse_mode=ParseMode.MARKDOWN,
    )
    STATE["status_msg_id"] = status.id

    delay = float(cfg_get("delay", 0.5))
    src_topic = int(cfg_get("source_topic", 0))
    source_chat_int = int(source_chat)

    processed = 0
    last_update = 0

    try:
        # STRICT SEQUENCE LOOP: first_id → last_id, ek ek karke
        for msg_id in range(first_id, last_id + 1):
            if STATE["stop"]:
                await update_status("🛑 **Stopped by user.**")
                break

            STATE["current_id"] = msg_id

            # Source topic filter ke liye pehle try: agar topic set hai to
            # forwarded message ka thread check karna padega — lekin direct forward se
            # topic match verify nahi hota. Isliye hum get_messages se verify karte hain.
            if src_topic > 0:
                try:
                    fetched = await client.get_messages(source_chat_int, msg_id)
                    if not fetched or fetched.empty:
                        STATE["skipped"] += 1
                        processed += 1
                        continue
                    thread_id = getattr(fetched, "message_thread_id", None) or \
                                (fetched.reply_to_message.id if fetched.reply_to_message else None)
                    if thread_id != src_topic:
                        STATE["skipped"] += 1
                        processed += 1
                        continue
                except Exception:
                    STATE["skipped"] += 1
                    processed += 1
                    continue

            ok = await forward_single(client, source_chat_int, msg_id)
            if ok:
                STATE["forwarded"] += 1
            else:
                # Agar message delete hai to failed nahi, skipped me daalo
                STATE["skipped"] += 1

            processed += 1

            # Har 20 messages pe status update
            if processed - last_update >= 20:
                last_update = processed
                await update_status(
                    f"🚀 **Range Forward Running**\n"
                    f"Range: `{first_id}` → `{last_id}`\n"
                    f"Current: `{msg_id}`\n"
                    f"`{processed}/{STATE['total']}`\n"
                    f"✅ OK: `{STATE['forwarded']}`  ⏭ Skip: `{STATE['skipped']}`"
                )

            await asyncio.sleep(delay)

        # final report
        if not STATE["stop"]:
            await update_status(
                f"✅ **Forward Complete**\n"
                f"Range: `{first_id}` → `{last_id}`\n"
                f"Total: `{STATE['total']}`\n"
                f"✅ Forwarded: `{STATE['forwarded']}`\n"
                f"⏭ Skipped: `{STATE['skipped']}`\n"
                f"❌ Failed: `{STATE['failed']}`"
            )
    except Exception as e:
        log.exception("Range forward error")
        await update_status(f"❌ **Error:** `{e}`")
    finally:
        STATE["running"] = False


# ---------------- LIVE MODE ----------------
@app.on_message(filters.command("live") & filters.user(OWNER_ID))
async def cmd_live_on(client, message: Message):
    if not cfg_get("source_chat") or not cfg_get("dest_chat"):
        return await message.reply("❌ Pehle source/dest set karo.")
    STATE["live"] = True
    await message.reply("🔴 **Live ON** — source ka har naya message forward hoga.")


@app.on_message(filters.command("liveoff") & filters.user(OWNER_ID))
async def cmd_live_off(client, message: Message):
    STATE["live"] = False
    await message.reply("⚪ Live OFF.")


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

    ok = await forward_single(client, message.chat.id, message.id)
    if ok:
        STATE["forwarded"] += 1
    else:
        STATE["skipped"] += 1

    await asyncio.sleep(float(cfg_get("delay", 0.5)))


log.info("Starting Advanced Range Forward Bot...")
app.run()
