from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database as db


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_or_create_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"🪪 *ur anon ID bestie:*\n\n"
        f"`{db_user['anonymous_id']}`\n\n"
        f"share this with ppl so they can find u on here 📤\n"
        f"_ur identity stays hidden tho, no cap_ 🤫✨",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ *Spillit Out — the vibe guide* 👻\n\n"
        "*ur commands bestie:*\n"
        "💌 `/confess @username` — anonymously spill ur feelings\n"
        "🪪 `/myid` — see ur anonymous ID\n"
        "⚙️ `/settings` — manage ur vibe settings\n"
        "🚩 `/report <id> <reason>` — report something sus\n"
        "❌ `/cancel` — abort mission\n\n"
        "*how it works fr:*\n"
        "1️⃣ someone sends u a confession 💌\n"
        "2️⃣ u decide: post it, keep it, reply, or delete 👀\n"
        "3️⃣ zero names revealed, ever 🔒\n\n"
        "*🔥 crush match feature:*\n"
        "if u and someone BOTH confess to each other??\n"
        "u BOTH get a match notification omg 😭💗\n\n"
        "_stay safe, stay kind, and spill responsibly_ 🌸"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "🚩 *to report something sketchy:*\n\n"
            "use: `/report <confession_id> <reason>`\n\n"
            "example: `/report 42 this is so rude omg`\n\n"
            "_we take reports seriously bestie_ 💪",
            parse_mode="Markdown",
        )
        return

    confession_id_str, *reason_parts = args
    if not confession_id_str.isdigit():
        await update.message.reply_text(
            "😭 bestie the confession ID needs to be a number\n"
            "like `/report 42 reason` not letters 💀"
        )
        return

    confession_id = int(confession_id_str)
    reason = " ".join(reason_parts)

    confession = db.get_confession(confession_id)
    if not confession:
        await update.message.reply_text(
            "🤔 hmm can't find that confession bestie\n"
            "double check the ID? 👀"
        )
        return

    db.create_report(
        reporter_id=update.effective_user.id,
        confession_id=confession_id,
        reason=reason,
    )
    await update.message.reply_text(
        "✅ *report sent!!* our admins will check it out 🔍\n\n"
        "thank u for keeping the vibe safe bestie 🫶🌸",
        parse_mode="Markdown",
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_or_create_user(user.id, user.username, user.first_name)

    confess_status = "✅ on!!" if db_user["allow_confess"] else "❌ off"
    dm_status = "✅ on!!" if db_user["allow_dm"] else "❌ off"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"💌 receive confessions: {confess_status}",
            callback_data="toggle_allow_confess"
        )],
        [InlineKeyboardButton(
            f"💬 anon replies: {dm_status}",
            callback_data="toggle_allow_dm"
        )],
    ])

    await update.message.reply_text(
        "⚙️ *ur vibe settings bestie* 🌸\n\n"
        "tap to toggle what u want 👇",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def toggle_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = db.get_user_by_telegram_id(user.id)
    if not db_user:
        return

    field = query.data.replace("toggle_", "")
    if field not in ("allow_confess", "allow_dm"):
        return

    new_val = 0 if db_user[field] else 1
    db.update_setting(user.id, field, new_val)

    db_user = db.get_user_by_telegram_id(user.id)
    confess_status = "✅ on!!" if db_user["allow_confess"] else "❌ off"
    dm_status = "✅ on!!" if db_user["allow_dm"] else "❌ off"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"💌 receive confessions: {confess_status}",
            callback_data="toggle_allow_confess"
        )],
        [InlineKeyboardButton(
            f"💬 anon replies: {dm_status}",
            callback_data="toggle_allow_dm"
        )],
    ])

    await query.edit_message_reply_markup(reply_markup=keyboard)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❎ *cancelled!!* ok bestie no worries 🌸\n"
        "come back when ur ready to spill 💅",
        parse_mode="Markdown",
    )
    return ConversationHandler.END
