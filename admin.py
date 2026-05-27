import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
import database as db

logger = logging.getLogger(__name__)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /ban <telegram_id or anon_id>")
        return

    target = _resolve_user(context.args[0])
    if not target:
        await update.message.reply_text("❌ User not found.")
        return

    db.ban_user(target["telegram_id"], banned=True)
    await update.message.reply_text(f"✅ User `{target['anonymous_id']}` has been banned.", parse_mode="Markdown")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /unban <telegram_id or anon_id>")
        return

    target = _resolve_user(context.args[0])
    if not target:
        await update.message.reply_text("❌ User not found.")
        return

    db.ban_user(target["telegram_id"], banned=False)
    await update.message.reply_text(f"✅ User `{target['anonymous_id']}` has been unbanned.", parse_mode="Markdown")


async def delete_confession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /delete <confession_id>")
        return

    confession_id = int(context.args[0])
    confession = db.get_confession(confession_id)

    if not confession:
        await update.message.reply_text("❌ Confession not found.")
        return

    db.update_confession_status(confession_id, "deleted")

    # Delete from group if posted
    group_chat_id = os.getenv("GROUP_CHAT_ID")
    if confession["group_msg_id"] and group_chat_id:
        try:
            await context.bot.delete_message(
                chat_id=group_chat_id,
                message_id=confession["group_msg_id"],
            )
        except Exception as e:
            logger.warning(f"Couldn't delete group message: {e}")

    await update.message.reply_text(f"✅ Confession #{confession_id} deleted.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    s = db.get_stats()
    text = (
        f"📊 *Bot Stats*\n\n"
        f"👤 Users: {s['users']}\n"
        f"💌 Total confessions: {s['total_confessions']}\n"
        f"✅ Approved: {s['approved']}\n"
        f"⏳ Pending: {s['pending']}\n"
        f"🔥 Matches: {s['matches']}\n"
        f"🚩 Reports: {s['reports']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def view_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    reports = db.get_all_reports()
    if not reports:
        await update.message.reply_text("No reports found.")
        return

    text = "🚩 *Recent Reports:*\n\n"
    for r in reports[:10]:
        text += f"• Report #{r['id']} | Confession: {r['confession_id']} | {r['reason'] or 'No reason'}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


def _resolve_user(identifier: str):
    """Resolve by telegram ID or anon ID."""
    if identifier.isdigit():
        return db.get_user_by_telegram_id(int(identifier))
    return db.get_user_by_anon_id(identifier)
