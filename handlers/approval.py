import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


def _get_admin_ids():
    return [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]


# ── Helper: build the channel post text ─────────────────────

def _build_channel_post(count: int, confession, receiver_label: str) -> str:
    """Build the formatted channel post with anonymous styling."""
    msg = confession["message"] or ""
    return (
        f"💌 *Confession #{count}*\n\n"
        f"🎯 *to:* _{receiver_label}_\n\n"
        f"❝ _{msg}_ ❞\n\n"
        f"🔒 _sender's identity is sealed forever_ 🤫\n"
        f"_sent anonymously via Spillit Out_ ✨"
    )


async def _get_receiver_label(confession) -> str:
    """Get a display label for who the confession is for."""
    if confession["target_description"]:
        # Path B — nameless confession
        return confession["target_description"]
    elif confession["receiver_id"]:
        # Path A — private confession, look up receiver
        receiver = db.get_user_by_telegram_id(confession["receiver_id"])
        if receiver:
            if receiver["username"]:
                return f"@{receiver['username']}"
            elif receiver["first_name"]:
                return receiver["first_name"]
    return "someone special 💗"


# ── Path A: Receiver clicks "📢 post it!!" → goes to admin queue ──

async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receiver clicked 'post it!!' — send to admin queue for final approval."""
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("😭 confession not found bestie, it's gone gone")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("bestie that's not ur confession to manage 💀", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"this confession was already {confession['status']} bestie 👀")
        return

    # Change status to admin_review
    db.update_confession_status(confession_id, "admin_review")

    # Get receiver label for admin preview
    receiver_label = await _get_receiver_label(confession)

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ approve & post!!", callback_data=f"admin_approve_{confession_id}"),
            InlineKeyboardButton("❌ reject it", callback_data=f"admin_reject_{confession_id}"),
        ]
    ])

    preview = confession["message"] or f"[{confession.get('media_type', 'media')}]"

    admin_msg = (
        f"📬 *confession needs ur approval bestie!!*\n\n"
        f"🎯 *to:* _{receiver_label}_\n\n"
        f"💌 *confession:*\n_{preview}_\n\n"
        f"_approve to post it to the channel_ 👇"
    )

    admin_ids = _get_admin_ids()
    for admin_id in admin_ids:
        try:
            if confession["media_type"] == "photo":
                await context.bot.send_photo(
                    chat_id=admin_id, photo=confession["media_file_id"],
                    caption=admin_msg, parse_mode="Markdown", reply_markup=admin_keyboard,
                )
            elif confession["media_type"] == "voice":
                await context.bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown", reply_markup=admin_keyboard)
                await context.bot.send_voice(chat_id=admin_id, voice=confession["media_file_id"])
            elif confession["media_type"] == "video":
                await context.bot.send_video(
                    chat_id=admin_id, video=confession["media_file_id"],
                    caption=admin_msg, parse_mode="Markdown", reply_markup=admin_keyboard,
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id, text=admin_msg,
                    parse_mode="Markdown", reply_markup=admin_keyboard,
                )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

    await query.edit_message_text(
        "📤 *sent to admin for review!!*\n\n"
        "if approved, it'll go live on the channel anonymously 🌍✨\n"
        "_ur identity stays hidden no cap_ 🔒",
        parse_mode="Markdown",
    )


async def handle_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("😭 confession not found bestie, it's gone gone")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("bestie that's not ur confession to manage 💀", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"this confession was already {confession['status']} bestie 👀")
        return

    db.update_confession_status(confession_id, "rejected")
    await query.edit_message_text(
        "🗑️ deleted! confession is gone gone 💨\n"
        "ur so powerful bestie 💅"
    )

    try:
        await context.bot.send_message(
            chat_id=confession["sender_id"],
            text=(
                "💔 oof bestie... ur confession wasn't posted publicly\n\n"
                "maybe they're just not ready yet 🥺\n"
                "don't give up on love fr fr 🌸"
            ),
        )
    except Exception:
        pass


async def handle_keep_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("😭 confession not found bestie, it's gone gone")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("bestie that's not ur confession to manage 💀", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"this confession was already {confession['status']} bestie 👀")
        return

    db.update_confession_status(confession_id, "private")
    await query.edit_message_text(
        "🔒 *kept private!* this stays between u two 🤫\n"
        "ur little secret, no cap ✨",
        parse_mode="Markdown",
    )


# ── Admin final approval: post to channel ───────────────────

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin clicked 'approve & post!!' — post to channel with full formatting."""
    query = update.callback_query
    await query.answer("posting to channel!! 🚀")

    confession_id = int(query.data.split("_")[2])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("😭 confession not found")
        return

    if confession["status"] not in ("admin_review", "pending"):
        await query.edit_message_text(f"already handled: {confession['status']}")
        return

    receiver_label = await _get_receiver_label(confession)
    count = db.count_approved_confessions() + 1
    post_text = _build_channel_post(count, confession, receiver_label)

    group_msg_id = None
    group_chat_id = os.getenv("GROUP_CHAT_ID")

    if group_chat_id:
        try:
            if confession["media_type"] == "photo":
                msg = await context.bot.send_photo(
                    chat_id=group_chat_id,
                    photo=confession["media_file_id"],
                    caption=f"💌 *Confession #{count}*\n\n🎯 *to:* _{receiver_label}_\n\n_{confession['message'] or ''}_\n\n🔒 _sender's identity is sealed forever_ 🤫",
                    parse_mode="Markdown",
                )
            elif confession["media_type"] == "voice":
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=f"💌 *Confession #{count}* 🎤\n\n🎯 *to:* _{receiver_label}_\n\n🔒 _sender's identity is sealed forever_ 🤫",
                    parse_mode="Markdown",
                )
                msg = await context.bot.send_voice(chat_id=group_chat_id, voice=confession["media_file_id"])
            elif confession["media_type"] == "video":
                msg = await context.bot.send_video(
                    chat_id=group_chat_id,
                    video=confession["media_file_id"],
                    caption=f"💌 *Confession #{count}*\n\n🎯 *to:* _{receiver_label}_\n\n_{confession['message'] or ''}_\n\n🔒 _sender's identity is sealed forever_ 🤫",
                    parse_mode="Markdown",
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=post_text,
                    parse_mode="Markdown",
                )
            group_msg_id = msg.message_id
        except Exception as e:
            logger.error(f"Failed to post confession to channel: {e}")
            await query.edit_message_text(
                f"❌ failed to post to channel!\n\nerror: {e}\n\n"
                "make sure the bot is an admin in the channel with 'Post Messages' permission 🙏"
            )
            return

    db.update_confession_status(confession_id, "approved", group_msg_id)

    await query.edit_message_text(
        f"✅ *posted to channel!!* 🎉\n\n"
        f"confession #{count} is now live for everyone to see 🌍",
        parse_mode="Markdown",
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=confession["sender_id"],
            text=(
                "🎉 *SLAY!!* ur confession got *approved* and posted to the channel!! 🎊\n\n"
                "it's officially out there bestie, no turning back now 😭💗"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # Notify receiver (path A only — they chose to post)
    if confession["receiver_id"]:
        try:
            await context.bot.send_message(
                chat_id=confession["receiver_id"],
                text=(
                    "📢 *the confession u approved just went live!!* 🌍✨\n"
                    "go check the channel bestie 👀💅"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin clicked 'reject it' — reject the confession."""
    query = update.callback_query
    await query.answer("rejected 🗑️")

    confession_id = int(query.data.split("_")[2])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("😭 confession not found")
        return

    if confession["status"] not in ("admin_review", "pending"):
        await query.edit_message_text(f"already handled: {confession['status']}")
        return

    db.update_confession_status(confession_id, "rejected")
    await query.edit_message_text("🗑️ *confession rejected!*\nnot posting this one 💅", parse_mode="Markdown")

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=confession["sender_id"],
            text=(
                "💔 oof bestie... ur confession wasn't approved for posting\n\n"
                "maybe try again with different words? 🥺\n"
                "keep the energy kind and cute 🌸"
            ),
        )
    except Exception:
        pass
