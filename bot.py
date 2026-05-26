import logging
import os
from dotenv import load_dotenv

# ── Load .env FIRST before any handler imports so all os.getenv() calls work ──
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import database as db
import handlers.start as start_handler
import handlers.confess as confess_handler
import handlers.approval as approval_handler
import handlers.replies as replies_handler
import handlers.match as match_handler
import handlers.admin as admin_handler
import handlers.misc as misc_handler
from middleware.rate_limit import rate_limit_middleware

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_CONFESSION = 1
WAITING_REPLY = 2


async def post_init(application: Application) -> None:
    """Initialize database on startup."""
    db.init_db()
    logger.info("Database initialized.")


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN not set in .env file!")

    app = Application.builder().token(token).post_init(post_init).build()

    # ── /start ──
    app.add_handler(CommandHandler("start", start_handler.start))

    # ── /myid ──
    app.add_handler(CommandHandler("myid", misc_handler.myid))

    # ── /help ──
    app.add_handler(CommandHandler("help", misc_handler.help_command))

    # ── /report ──
    app.add_handler(CommandHandler("report", misc_handler.report_command))

    # ── /settings ──
    app.add_handler(CommandHandler("settings", misc_handler.settings_command))

    # ── /confess conversation ──
    confess_conv = ConversationHandler(
        entry_points=[CommandHandler("confess", confess_handler.confess_start)],
        states={
            WAITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confess_handler.confess_receive),
                MessageHandler(filters.PHOTO | filters.VOICE | filters.VIDEO, confess_handler.confess_media),
            ],
        },
        fallbacks=[CommandHandler("cancel", misc_handler.cancel)],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(confess_conv)

    # ── Anonymous reply conversation ──
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(replies_handler.reply_start, pattern=r"^reply_\d+$")],
        states={
            WAITING_REPLY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, replies_handler.reply_receive),
            ],
        },
        fallbacks=[CommandHandler("cancel", misc_handler.cancel)],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(reply_conv)

    # ── Approval buttons ──
    app.add_handler(CallbackQueryHandler(approval_handler.handle_approve, pattern=r"^approve_\d+$"))
    app.add_handler(CallbackQueryHandler(approval_handler.handle_reject, pattern=r"^reject_\d+$"))
    app.add_handler(CallbackQueryHandler(approval_handler.handle_keep_private, pattern=r"^private_\d+$"))
    app.add_handler(CallbackQueryHandler(approval_handler.admin_approve, pattern=r"^admin_approve_\d+$"))
    app.add_handler(CallbackQueryHandler(approval_handler.admin_reject, pattern=r"^admin_reject_\d+$"))

    # ── Settings toggles ──
    app.add_handler(CallbackQueryHandler(misc_handler.toggle_setting, pattern=r"^toggle_"))

    # ── Admin commands ──
    app.add_handler(CommandHandler("ban", admin_handler.ban_user))
    app.add_handler(CommandHandler("unban", admin_handler.unban_user))
    app.add_handler(CommandHandler("delete", admin_handler.delete_confession))
    app.add_handler(CommandHandler("stats", admin_handler.stats))
    app.add_handler(CommandHandler("reports", admin_handler.view_reports))

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
