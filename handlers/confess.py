import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import handlers.match as match_handler

logger = logging.getLogger(__name__)

WAITING_CONFESSION = 1


def _get_admin_ids():
    return [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]


async def confess_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    db_user = db.get_or_create_user(sender.id, sender.username, sender.first_name)

    if db_user["banned"]:
        await update.message.reply_text("💀 bestie u got banned\nnot ur day fr fr 😭")
        return ConversationHandler.END

    if not db.check_rate_limit(sender.id, "confess", max_count=10, window_minutes=60):
        await update.message.reply_text(
            "⏳ okay okay slow down bestie 😭\n"
            "ur sending TOO many confessions omg\n"
            "take a breath and try again in a bit 🌸"
        )
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text(
            "🫣 *how to spill bestie:*\n\n"
            "👤 *Know their username?*\n"
            "`/confess @username` → confession goes to them privately first\n\n"
            "🤷 *Don't know their username?*\n"
            "`/confess sarah from class 5` → goes straight to admin for posting\n\n"
            "_either way — ur identity stays hidden forever_ 🤫💗",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # ── Path A: Know their @username ──────────────────────────
    if args[0].startswith("@"):
        target_input = args[0].lstrip("@")
        target = db.get_user_by_username(target_input)
        if not target:
            target = db.get_user_by_anon_id(target_input)

        if not target:
            await update.message.reply_text(
                f"😭 can't find *@{target_input}* bestie\n\n"
                f"they need to start the bot first by sending `/start`\n"
                f"tell them to get on it!! 🫶\n\n"
                f"_or if u don't know their username, try:_\n"
                f"`/confess their name or description`",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        if target["telegram_id"] == sender.id:
            await update.message.reply_text(
                "💀 bestie u cannot confess to YOURSELF\n"
                "self love is cute but not like this 😭✋"
            )
            return ConversationHandler.END

        if target["banned"]:
            await update.message.reply_text("🚫 oof that user isn't available rn 🥺")
            return ConversationHandler.END

        if not target["allow_confess"]:
            await update.message.reply_text(
                "🔒 they've got confessions turned OFF\n"
                "not accepting feelings rn 💔 respect it bestie"
            )
            return ConversationHandler.END

        context.user_data["confess_mode"] = "private"
        context.user_data["confession_target"] = target["telegram_id"]
        context.user_data["confession_target_name"] = (
            f"@{target['username']}" if target["username"] else target["first_name"]
        )

        target_display = f"@{target['username']}" if target["username"] else target["first_name"]

        await update.message.reply_text(
            f"🫶 *ok bestie let's go!!*\n\n"
            f"type ur confession to *{target_display}* 👇\n\n"
            f"u can send: 💬 text • 📸 photo • 🎤 voice • 🎬 video\n\n"
            f"_they'll NEVER know it was u, no cap_ 🤫✨\n\n"
            f"type /cancel if ur having second thoughts 😅",
            parse_mode="Markdown",
        )
        return WAITING_CONFESSION

    # ── Path B: Don't know their username — describe them ─────
    else:
        target_description = " ".join(args)  # e.g. "sarah from class 5"

        context.user_data["confess_mode"] = "public"
        context.user_data["target_description"] = target_description

        await update.message.reply_text(
            f"💌 *spilling to: \"{target_description}\"*\n\n"
            f"type ur confession below 👇\n"
            f"admin will review it before it goes live on the channel 🔍\n\n"
            f"u can send: 💬 text • 📸 photo • 🎤 voice • 🎬 video\n\n"
            f"_still 100% anonymous bestie_ 🤫✨\n\n"
            f"type /cancel to abort 😅",
            parse_mode="Markdown",
        )
        return WAITING_CONFESSION


async def confess_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    message_text = update.message.text
    mode = context.user_data.get("confess_mode", "private")

    if _is_harmful(message_text):
        await update.message.reply_text(
            "🚨 yikes bestie that message is giving red flags 🚩\n"
            "we don't do that here fr\n"
            "be kind, keep it cute 🌸"
        )
        return ConversationHandler.END

    if mode == "private":
        target_id = context.user_data.get("confession_target")
        if not target_id:
            await update.message.reply_text("😵 something broke, start over with /confess 🙏")
            return ConversationHandler.END

        confession_id = db.create_confession(
            sender_id=sender.id,
            receiver_id=target_id,
            message=message_text,
        )
        await _deliver_private(update, context, confession_id, target_id, message_text)

    else:  # public — nameless confession → admin queue
        target_description = context.user_data.get("target_description", "someone")
        confession_id = db.create_confession(
            sender_id=sender.id,
            receiver_id=None,
            message=message_text,
            target_description=target_description,
            status="admin_review",
        )
        await _deliver_to_admin_queue(update, context, confession_id, target_description, message_text)

    return ConversationHandler.END


async def confess_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    mode = context.user_data.get("confess_mode", "private")

    msg = update.message
    media_type, file_id, caption = None, None, msg.caption or ""

    if msg.photo:
        media_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.voice:
        media_type = "voice"
        file_id = msg.voice.file_id
    elif msg.video:
        media_type = "video"
        file_id = msg.video.file_id

    if mode == "private":
        target_id = context.user_data.get("confession_target")
        if not target_id:
            await update.message.reply_text("😵 something broke, start over with /confess 🙏")
            return ConversationHandler.END

        confession_id = db.create_confession(
            sender_id=sender.id,
            receiver_id=target_id,
            message=caption if caption else None,
            media_type=media_type,
            media_file_id=file_id,
        )
        await _deliver_private(
            update, context, confession_id, target_id,
            caption or f"[{media_type}]", media_type=media_type, file_id=file_id
        )

    else:  # public
        target_description = context.user_data.get("target_description", "someone")
        confession_id = db.create_confession(
            sender_id=sender.id,
            receiver_id=None,
            message=caption if caption else None,
            media_type=media_type,
            media_file_id=file_id,
            target_description=target_description,
            status="admin_review",
        )
        await _deliver_to_admin_queue(
            update, context, confession_id, target_description,
            caption or f"[{media_type}]", media_type=media_type, file_id=file_id
        )

    return ConversationHandler.END


# ── Private delivery (Path A) ────────────────────────────────

async def _deliver_private(update, context, confession_id, target_id, preview_text, media_type=None, file_id=None):
    sender = update.effective_user

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 post it!!", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("🗑️ nah delete", callback_data=f"reject_{confession_id}"),
        ],
        [
            InlineKeyboardButton("💬 reply anonymously", callback_data=f"reply_{confession_id}"),
            InlineKeyboardButton("🔒 keep it private", callback_data=f"private_{confession_id}"),
        ],
    ])

    header = "💌 *omg u got an anonymous confession!!* 👀\n\n"

    try:
        if media_type == "photo":
            await context.bot.send_photo(
                chat_id=target_id, photo=file_id,
                caption=f"{header}{preview_text}" if preview_text else header,
                parse_mode="Markdown", reply_markup=keyboard,
            )
        elif media_type == "voice":
            await context.bot.send_message(chat_id=target_id, text=header, parse_mode="Markdown")
            await context.bot.send_voice(chat_id=target_id, voice=file_id, reply_markup=keyboard)
        elif media_type == "video":
            await context.bot.send_video(
                chat_id=target_id, video=file_id,
                caption=f"{header}{preview_text}" if preview_text else header,
                parse_mode="Markdown", reply_markup=keyboard,
            )
        else:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"{header}_{preview_text}_\n\n_what r u gonna do with this bestie?_ 👀",
                parse_mode="Markdown", reply_markup=keyboard,
            )

        await update.message.reply_text(
            "✅ *sent!!* ur confession is on its way 🚀\n\n"
            "now we wait 🫣 fingers crossed bestie 🤞💗",
            parse_mode="Markdown",
        )
        await match_handler.check_and_notify_match(context, sender.id, target_id)

    except Exception as e:
        logger.error(f"Failed to deliver confession {confession_id}: {e}")
        await update.message.reply_text(
            "😭 oof couldn't deliver ur confession\n"
            "they might've blocked the bot or never started it\n"
            "tell them to message /start first! 🙏"
        )
        db.update_confession_status(confession_id, "failed")


# ── Admin queue delivery (Path B) ────────────────────────────

async def _deliver_to_admin_queue(update, context, confession_id, target_description, preview_text, media_type=None, file_id=None):
    admin_ids = _get_admin_ids()

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ approve & post", callback_data=f"admin_approve_{confession_id}"),
            InlineKeyboardButton("❌ reject", callback_data=f"admin_reject_{confession_id}"),
        ]
    ])

    admin_header = (
        f"📬 *new confession needs ur approval!!*\n\n"
        f"👤 *to:* _{target_description}_\n\n"
        f"💌 *confession:*\n"
    )

    for admin_id in admin_ids:
        try:
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=admin_id, photo=file_id,
                    caption=f"{admin_header}{preview_text}",
                    parse_mode="Markdown", reply_markup=admin_keyboard,
                )
            elif media_type == "voice":
                await context.bot.send_message(chat_id=admin_id, text=admin_header, parse_mode="Markdown")
                await context.bot.send_voice(chat_id=admin_id, voice=file_id, reply_markup=admin_keyboard)
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=admin_id, video=file_id,
                    caption=f"{admin_header}{preview_text}",
                    parse_mode="Markdown", reply_markup=admin_keyboard,
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"{admin_header}_{preview_text}_",
                    parse_mode="Markdown", reply_markup=admin_keyboard,
                )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

    await update.message.reply_text(
        "✅ *confession submitted!!* 🎉\n\n"
        "admin will review it before it goes live 🔍\n"
        "if approved, it'll be posted anonymously to the channel 📢\n\n"
        "_ur identity stays hidden no matter what_ 🤫💗",
        parse_mode="Markdown",
    )


def _is_harmful(text: str) -> bool:
    if not text:
        return False
    banned_words = ["kill yourself", "kys", "suicide", "bomb", "threat", "hack", "doxx"]
    return any(word in text.lower() for word in banned_words)
