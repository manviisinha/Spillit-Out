import logging
from telegram.ext import ContextTypes
import database as db

logger = logging.getLogger(__name__)


async def check_and_notify_match(context: ContextTypes.DEFAULT_TYPE, sender_id: int, receiver_id: int):
    """
    Check if both users have confessed to each other.
    If yes and not already matched → notify both with a 🔥 match alert.
    """
    if not db.check_mutual_confession(sender_id, receiver_id):
        return

    is_new_match = db.record_match(sender_id, receiver_id)
    if not is_new_match:
        return

    match_msg = (
        "🔥 *It's a match!*\n\n"
        "Someone you confessed to has *also* confessed to you! 👀\n\n"
        "You both have feelings for each other. Maybe it's time to make a move? 😏"
    )

    try:
        await context.bot.send_message(chat_id=sender_id, text=match_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Match notify failed for {sender_id}: {e}")

    try:
        await context.bot.send_message(chat_id=receiver_id, text=match_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Match notify failed for {receiver_id}: {e}")
