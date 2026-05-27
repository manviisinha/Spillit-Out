import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")


async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("❌ Confession not found.")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("This isn't your confession to manage.", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"This confession was already {confession['status']}.")
        return

    # Post to group
    count = db.count_approved_confessions() + 1
    post_text = f"💬 *Confession #{count}*\n\n_{confession['message'] or ''}_ "

    group_msg_id = None
    if GROUP_CHAT_ID:
        try:
            if confession["media_type"] == "photo":
                msg = await context.bot.send_photo(
                    chat_id=GROUP_CHAT_ID,
                    photo=confession["media_file_id"],
                    caption=f"💬 *Confession #{count}*\n\n_{confession['message'] or ''}_",
                    parse_mode="Markdown",
                )
            elif confession["media_type"] == "voice":
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"💬 *Confession #{count}*", parse_mode="Markdown")
                msg = await context.bot.send_voice(chat_id=GROUP_CHAT_ID, voice=confession["media_file_id"])
            elif confession["media_type"] == "video":
                msg = await context.bot.send_video(
                    chat_id=GROUP_CHAT_ID,
                    video=confession["media_file_id"],
                    caption=f"💬 *Confession #{count}*\n\n_{confession['message'] or ''}_",
                    parse_mode="Markdown",
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=post_text,
                    parse_mode="Markdown",
                )
            group_msg_id = msg.message_id
        except Exception as e:
            logger.error(f"Failed to post confession to group: {e}")

    db.update_confession_status(confession_id, "approved", group_msg_id)

    await query.edit_message_text(
        "✅ *Confession approved and posted anonymously!*",
        parse_mode="Markdown",
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=confession["sender_id"],
            text=f"🎉 Your confession was *approved* and posted to the group!",
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def handle_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("❌ Confession not found.")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("This isn't your confession to manage.", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"This confession was already {confession['status']}.")
        return

    db.update_confession_status(confession_id, "rejected")
    await query.edit_message_text("🗑️ Confession rejected.")

    # Notify sender (without revealing who rejected)
    try:
        await context.bot.send_message(
            chat_id=confession["sender_id"],
            text="💔 Your confession was not posted publicly.",
        )
    except Exception:
        pass


async def handle_keep_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("❌ Confession not found.")
        return

    if confession["receiver_id"] != query.from_user.id:
        await query.answer("This isn't your confession to manage.", show_alert=True)
        return

    if confession["status"] != "pending":
        await query.edit_message_text(f"This confession was already {confession['status']}.")
        return

    db.update_confession_status(confession_id, "private")
    await query.edit_message_text(
        "🔒 *Kept private.* This confession stays between you and the sender.",
        parse_mode="Markdown",
    )
