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
        await query.edit_message_text("😭 confession not found bestie, it's gone gone")
        return ConversationHandler.END

    user = query.from_user

    if confession["receiver_id"] != user.id:
        await query.answer("u can only reply to confessions sent to u bestie 💀", show_alert=True)
        return ConversationHandler.END

    context.user_data["reply_confession_id"] = confession_id
    context.user_data["reply_to"] = confession["sender_id"]

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "💬 *ur about to reply anonymously!!* 🫣\n\n"
            "type whatever u wanna say bestie\n"
            "they won't know it's u, promise 🤫🌸\n\n"
            "type /cancel if u change ur mind 😅"
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
        await update.message.reply_text(
            "😵 omg something went wrong bestie\n"
            "try again from the start 🙏"
        )
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
                f"💬 *someone replied to ur confession!!* 👀\n\n"
                f"_ur confession: \"{preview}...\"_\n\n"
                f"✨ *their reply:*\n{reply_text}\n\n"
                f"_u can reply back anonymously too!!_ 🫶"
            ),
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            "✅ *reply sent!!* they got ur message 🚀\n"
            "still anonymous, still iconic 💅✨",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send reply: {e}")
        await update.message.reply_text(
            "😭 couldn't send ur reply bestie\n"
            "they might've blocked the bot 💔"
        )

    return ConversationHandler.END
