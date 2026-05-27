import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db

logger = logging.getLogger(__name__)
WAITING_REPLY = 2


async def reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confession_id = int(query.data.split("_")[1])
    confession = db.get_confession(confession_id)

    if not confession:
        await query.edit_message_text("❌ Confession not found.")
        return ConversationHandler.END

    user = query.from_user

    # Only receiver can reply to the confession
    if confession["receiver_id"] != user.id:
        await query.answer("You can only reply to confessions sent to you.", show_alert=True)
        return ConversationHandler.END

    context.user_data["reply_confession_id"] = confession_id
    context.user_data["reply_to"] = confession["sender_id"]

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "💬 *Reply anonymously*\n\n"
            "Type your reply below. The sender won't know who you are.\n\n"
            "Type /cancel to abort."
        ),
        parse_mode="Markdown",
    )
    return WAITING_REPLY


async def reply_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reply_text = update.message.text

    confession_id = context.user_data.get("reply_confession_id")
    reply_to = context.user_data.get("reply_to")

    if not confession_id or not reply_to:
        await update.message.reply_text("Something went wrong. Please try again.")
        return ConversationHandler.END

    db.create_reply(
        confession_id=confession_id,
        sender_id=user.id,
        receiver_id=reply_to,
        message=reply_text,
    )

    confession = db.get_confession(confession_id)
    preview = (confession["message"] or "[media]")[:40]

    try:
        await context.bot.send_message(
            chat_id=reply_to,
            text=(
                f"💬 *Anonymous reply to your confession:*\n\n"
                f"_Your confession: \"{preview}...\"_\n\n"
                f"*Reply:* {reply_text}"
            ),
            parse_mode="Markdown",
        )
        await update.message.reply_text("✅ *Reply sent anonymously!*", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send reply: {e}")
        await update.message.reply_text("⚠️ Couldn't deliver your reply. The user may have blocked the bot.")

    return ConversationHandler.END
