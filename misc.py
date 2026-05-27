from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database as db


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_or_create_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"🪪 Your anonymous ID is: `{db_user['anonymous_id']}`\n\n"
        f"Share this with people so they can send you confessions.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👻 *CampusWhisper Help*\n\n"
        "*Commands:*\n"
        "• `/start` — Register & get your anonymous ID\n"
        "• `/myid` — See your anonymous ID\n"
        "• `/confess <ID>` — Send an anonymous confession\n"
        "• `/settings` — Manage your privacy settings\n"
        "• `/report <confession_id> <reason>` — Report a confession\n"
        "• `/cancel` — Cancel current action\n\n"
        "*How it works:*\n"
        "1. Share your anonymous ID with friends\n"
        "2. They send you a confession via the bot\n"
        "3. You choose: post publicly, reply, or keep private\n"
        "4. No names are ever revealed 🔒\n\n"
        "*Crush Match:*\n"
        "If you and someone both confess to each other — you'll both get a 🔥 match alert!\n\n"
        "_Stay safe. Be kind._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/report <confession_id> <reason>`\n\nExample: `/report 42 harassment`",
            parse_mode="Markdown",
        )
        return

    confession_id_str, *reason_parts = args
    if not confession_id_str.isdigit():
        await update.message.reply_text("❌ Confession ID must be a number.")
        return

    confession_id = int(confession_id_str)
    reason = " ".join(reason_parts)

    confession = db.get_confession(confession_id)
    if not confession:
        await update.message.reply_text("❌ Confession not found.")
        return

    db.create_report(
        reporter_id=update.effective_user.id,
        confession_id=confession_id,
        reason=reason,
    )
    await update.message.reply_text(
        "✅ *Report submitted.* Our admins will review it shortly.\n\nThank you for keeping the community safe.",
        parse_mode="Markdown",
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_or_create_user(user.id, user.username, user.first_name)

    confess_status = "✅ On" if db_user["allow_confess"] else "❌ Off"
    dm_status = "✅ On" if db_user["allow_dm"] else "❌ Off"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"Receive confessions: {confess_status}",
            callback_data="toggle_allow_confess"
        )],
        [InlineKeyboardButton(
            f"Anonymous replies: {dm_status}",
            callback_data="toggle_allow_dm"
        )],
    ])

    await update.message.reply_text(
        "⚙️ *Your Settings*\n\nTap a setting to toggle it:",
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

    # Refresh settings view
    db_user = db.get_user_by_telegram_id(user.id)
    confess_status = "✅ On" if db_user["allow_confess"] else "❌ Off"
    dm_status = "✅ On" if db_user["allow_dm"] else "❌ Off"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"Receive confessions: {confess_status}",
            callback_data="toggle_allow_confess"
        )],
        [InlineKeyboardButton(
            f"Anonymous replies: {dm_status}",
            callback_data="toggle_allow_dm"
        )],
    ])

    await query.edit_message_reply_markup(reply_markup=keyboard)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❎ Cancelled.")
    return ConversationHandler.END
