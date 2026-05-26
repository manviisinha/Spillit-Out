"""
Rate limiting middleware for the Telegram bot.
This module provides a simple rate limiting decorator/function
that can be used to limit how often users can trigger actions.
"""
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


def rate_limit_middleware(action: str, max_count: int = 5, window_minutes: int = 60):
    """
    Decorator to apply rate limiting to a handler function.

    Usage:
        @rate_limit_middleware("confess", max_count=10, window_minutes=60)
        async def my_handler(update, context):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user
            if user is None:
                return await func(update, context, *args, **kwargs)

            allowed = db.check_rate_limit(user.id, action, max_count, window_minutes)
            if not allowed:
                if update.message:
                    await update.message.reply_text(
                        f"⏳ You're doing that too often. Please wait before trying again."
                    )
                elif update.callback_query:
                    await update.callback_query.answer(
                        "You're doing that too often. Please wait.", show_alert=True
                    )
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
