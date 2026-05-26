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
        "🔥 *IT'S A MATCH BESTIE!!* 🔥\n\n"
        "okay so this is INSANE 😭💗\n"
        "someone u confessed to *also* confessed to u!!\n\n"
        "u both have feelings for each other fr fr 👀✨\n\n"
        "maybe it's time to shoot ur shot irl?? 😏🏹\n"
        "_the universe is literally pushing u two together_ 🌸"
    )

    try:
        await context.bot.send_message(chat_id=sender_id, text=match_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Match notify failed for {sender_id}: {e}")

    try:
        await context.bot.send_message(chat_id=receiver_id, text=match_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Match notify failed for {receiver_id}: {e}")
