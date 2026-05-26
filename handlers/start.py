import logging
from telegram import Update
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_or_create_user(user.id, user.username, user.first_name)

    if db_user["banned"]:
        await update.message.reply_text(
            "💀 bestie you got banned lmaooo\n"
            "not ur day fr fr 😭"
        )
        return

    await update.message.reply_text(
        f"heyy {user.first_name}!! welcome to *Spillit Out* 🌸✨\n\n"
        f"where the tea gets spilled *anonymously* 👀💅\n\n"
        f"here's the vibe check:\n"
        f"• someone sends u a confession 💌\n"
        f"• u decide what to do with it 🫣\n"
        f"• no one EVER finds out who sent it 🤫🔒\n\n"
        f"*ur commands bestie:*\n"
        f"💬 `/confess @username` — spill ur feelings\n"
        f"🪪 `/myid` — flex ur anon ID\n"
        f"⚙️ `/settings` — ur vibe settings\n"
        f"📖 `/help` — full guide bestie\n\n"
        f"_go ahead, be brave, shoot ur shot_ 🏹💗\n"
        f"no cap, they'll never know it was u 🤭",
        parse_mode="Markdown",
    )
