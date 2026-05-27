import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import handlers.match as match_handler

logger = logging.getLogger(__name__)

WAITING_CONFESSION = 1
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # set this in .env


async def confess_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    db_user = db.get_or_create_user(sender.id, sender.username, sender.first_name)

    if db_user["banned"]:
        await update.message.reply_text("❌ You are banned from using this bot.")
        return ConversationHandler.END

    # Rate limit: max 10 confessions per hour
    if not db.check_rate_limit(sender.id, "confess", max_count=10, window_minutes=60):
        await update.message.reply_text(
            "⏳ You're sending too many confessions. Please wait a bit before sending more."
        )
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/confess <Anonymous ID>`\n\nExample: `/confess A4821`",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    target_anon_id = args[0].upper()
    target = db.get_user_by_anon_id(target_anon_id)

    if not target:
        await update.message.reply_text(
            f"❌ No user found with ID `{target_anon_id}`. Check the ID and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if target["telegram_id"] == sender.id:
        await update.message.reply_text("😅 You can't confess to yourself!")
        return ConversationHandler.END

    if target["banned"]:
        await update.message.reply_text("❌ That user is not available.")
        return ConversationHandler.END

    if not target["allow_confess"]:
        await update.message.reply_text("🔒 That user has disabled receiving confessions.")
        return ConversationHandler.END

    # Store target in context
    context.user_data["confession_target"] = target["telegram_id"]
    context.user_data["confession_target_anon"] = target_anon_id

    await update.message.reply_text(
        f"✍️ *Send your anonymous confession to `{target_anon_id}`*\n\n"
        f"You can send:\n• Text message\n• Photo\n• Voice note\n• Video\n\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown",
    )
    return WAITING_CONFESSION


async def confess_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    message_text = update.message.text
    target_id = context.user_data.get("confession_target")

    if not target_id:
        await update.message.reply_text("Something went wrong. Please start over with /confess")
        return ConversationHandler.END

    # AI content moderation check (basic keyword filter — swap for AI in Phase 2)
    if _is_harmful(message_text):
        await update.message.reply_text(
            "⚠️ Your message was flagged for potentially harmful content and was not sent.\n"
            "Please keep confessions respectful."
        )
        return ConversationHandler.END

    confession_id = db.create_confession(
        sender_id=sender.id,
        receiver_id=target_id,
        message=message_text,
    )

    await _deliver_confession(update, context, confession_id, target_id, message_text)
    return ConversationHandler.END


async def confess_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    target_id = context.user_data.get("confession_target")

    if not target_id:
        await update.message.reply_text("Something went wrong. Please start over with /confess")
        return ConversationHandler.END

    msg = update.message
    media_type, file_id, caption = None, None, msg.caption or ""

    if msg.photo:
        media_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.voice:
        media_type = "voice"
        file_id = msg.voice.file_id
    elif msg.video:
        media_type = "video"
        file_id = msg.video.file_id

    confession_id = db.create_confession(
        sender_id=sender.id,
        receiver_id=target_id,
        message=caption if caption else None,
        media_type=media_type,
        media_file_id=file_id,
    )

    await _deliver_confession(update, context, confession_id, target_id, caption or f"[{media_type}]", media_type=media_type, file_id=file_id)
    return ConversationHandler.END


async def _deliver_confession(update, context, confession_id, target_id, preview_text, media_type=None, file_id=None):
    sender = update.effective_user

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Post", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}"),
        ],
        [
            InlineKeyboardButton("💬 Reply Anonymously", callback_data=f"reply_{confession_id}"),
            InlineKeyboardButton("🔒 Keep Private", callback_data=f"private_{confession_id}"),
        ],
    ])

    header = "💌 *You received an anonymous confession:*\n\n"

    try:
        if media_type == "photo":
            await context.bot.send_photo(
                chat_id=target_id,
                photo=file_id,
                caption=f"{header}{preview_text}" if preview_text else header,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        elif media_type == "voice":
            await context.bot.send_message(chat_id=target_id, text=header, parse_mode="Markdown")
            await context.bot.send_voice(chat_id=target_id, voice=file_id, reply_markup=keyboard)
        elif media_type == "video":
            await context.bot.send_video(
                chat_id=target_id,
                video=file_id,
                caption=f"{header}{preview_text}" if preview_text else header,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"{header}_{preview_text}_",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

        await update.message.reply_text(
            "✅ *Confession sent anonymously!*\n\nYou'll be notified if they reply.",
            parse_mode="Markdown",
        )

        # Check for mutual crush match
        await match_handler.check_and_notify_match(context, sender.id, target_id)

    except Exception as e:
        logger.error(f"Failed to deliver confession {confession_id}: {e}")
        await update.message.reply_text(
            "⚠️ Couldn't deliver the confession. The user may have blocked the bot."
        )
        db.update_confession_status(confession_id, "failed")


def _is_harmful(text: str) -> bool:
    """Basic keyword filter. Replace with AI moderation in Phase 2."""
    if not text:
        return False
    banned_words = [
        "kill yourself", "kys", "suicide", "bomb", "threat", "hack", "doxx",
    ]
    text_lower = text.lower()
    return any(word in text_lower for word in banned_words)
