from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from config import (
    TIER_BOUNDARIES, MIN_VOTES, ALLOWED_CHAT_ID,
    ACCESS_MODE, ALLOWED_USERS, ADMIN_ID
)
import database as db

WAITING_PHOTO, WAITING_NAME, WAITING_CONTACT = range(3)


# ========== Access Control ==========

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID


def is_user_allowed(user_id: int) -> bool:
    if ACCESS_MODE != "whitelist":
        return True
    if _is_admin(user_id):
        return True
    # Check both .env list and DB
    if user_id in ALLOWED_USERS:
        return True
    return db.is_in_whitelist(user_id)


def check_chat(update: Update) -> bool:
    if ALLOWED_CHAT_ID is None:
        return True
    return update.effective_chat.id == ALLOWED_CHAT_ID


async def _guard(update: Update) -> bool:
    """Returns True if access is DENIED."""
    if not is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text(
            "You don't have access to this bot.\n"
            f"Your ID: `{update.effective_user.id}`\n"
            "Ask admin to add you via /allow",
            parse_mode="Markdown"
        )
        return True
    return False


# ========== /start ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    text = (
        "MANBOOK\n\n"
        "Commands:\n"
        "/add - add a girl (photo + name)\n"
        "/tierlist - show tier list\n"
        "/top - top 10\n"
        "/help - help\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ========== /myid ==========

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    allowed = "Access granted" if is_user_allowed(uid) else "No access"
    await update.message.reply_text(
        f"**{name}**\n"
        f"`{uid}`\n"
        f"{allowed}",
        parse_mode="Markdown"
    )


# ========== Admin Commands ==========

async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/allow 123456`\n"
            "Or `/allow 123456 789012 345678`",
            parse_mode="Markdown"
        )
        return

    added = []
    for arg in context.args:
        try:
            uid = int(arg)
            db.add_to_whitelist(uid)
            added.append(uid)
        except ValueError:
            pass

    if added:
        total = len(db.get_all_whitelist())
        await update.message.reply_text(
            f"Added: {', '.join(f'`{u}`' for u in added)}\n"
            f"Total in whitelist (DB): {total}",
            parse_mode="Markdown"
        )


async def deny_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/deny 123456`", parse_mode="Markdown")
        return

    removed = []
    for arg in context.args:
        try:
            uid = int(arg)
            db.remove_from_whitelist(uid)
            removed.append(uid)
        except ValueError:
            pass

    if removed:
        await update.message.reply_text(
            f"Removed: {', '.join(f'`{u}`' for u in removed)}",
            parse_mode="Markdown"
        )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return

    db_users = db.get_all_whitelist()
    env_users = sorted(ALLOWED_USERS)

    text = "**Whitelist:**\n\n"

    if env_users:
        text += "**From .env:**\n"
        for uid in env_users:
            text += f"  * `{uid}`\n"
        text += "\n"

    if db_users:
        text += "**From DB (added via /allow):**\n"
        for uid in db_users:
            text += f"  * `{uid}`\n"
        text += "\n"

    if not env_users and not db_users:
        text += "Empty.\n"

    all_unique = set(env_users) | set(db_users)
    text += f"Total unique: {len(all_unique)}"
    await update.message.reply_text(text, parse_mode="Markdown")


# ========== Add Girl ==========

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return ConversationHandler.END
    if not check_chat(update):
        return ConversationHandler.END
    await update.message.reply_text("Send a photo of the girl:")
    return WAITING_PHOTO


async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data["photo_file_id"] = photo.file_id
        await update.message.reply_text("Now enter her name (or nickname):")
        return WAITING_NAME
    else:
        await update.message.reply_text("That's not a photo. Send a photo:")
        return WAITING_PHOTO


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name or len(name) > 100:
        await update.message.reply_text("Name must be 1-100 characters. Try again:")
        return WAITING_NAME

    context.user_data["name"] = name

    keyboard = [[InlineKeyboardButton("Skip", callback_data="skip_contact")]]
    await update.message.reply_text(
        "Enter contact (@ or link), or press Skip:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_CONTACT


async def add_contact_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text.strip()
    context.user_data["contact"] = contact
    return await _finish_add(update, context)


async def add_contact_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["contact"] = None
    return await _finish_add(update, context, callback_query=query)


async def _broadcast_voting(
    context: ContextTypes.DEFAULT_TYPE,
    girl_id: int,
    name: str,
    photo_file_id: str,
    exclude_user: int = None
):
    """Sends voting to all users from whitelist."""
    keyboard = _build_vote_keyboard(girl_id)
    caption = f"**Rate: {name}**\nChoose a rating from 1 to 10:"

    # Collect all users: from .env + from DB
    all_users = set(ALLOWED_USERS) | set(db.get_all_whitelist())
    if ADMIN_ID:
        all_users.add(ADMIN_ID)

    for uid in all_users:
        if uid == exclude_user:
            continue
        try:
            msg = await context.bot.send_photo(
                chat_id=uid,
                photo=photo_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            db.save_active_poll(girl_id, uid, msg.message_id)
        except Exception:
            # User hasn't started chat with bot / blocked - skip
            pass


async def _finish_add(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_query=None):
    user_data = context.user_data
    photo_file_id = user_data["photo_file_id"]
    name = user_data["name"]
    contact = user_data.get("contact")
    submitted_by = update.effective_user.id

    girl_id = db.add_girl(name, contact, photo_file_id, submitted_by)

    # Broadcast voting to ALL users (including the submitter)
    await _broadcast_voting(context, girl_id, name, photo_file_id)

    text = f"**{name}** has been added! Voting started."
    if callback_query:
        await callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

    user_data.clear()
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Addition cancelled.")
    return ConversationHandler.END


# ========== Voting ==========

def _build_vote_keyboard(girl_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(str(i), callback_data=f"vote_{girl_id}_{i}"))
        if i % 5 == 0:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)


async def _start_voting(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    girl_id: int,
    name: str,
    photo_file_id: str
):
    keyboard = _build_vote_keyboard(girl_id)
    caption = f"**Rate: {name}**\nChoose a rating from 1 to 10:"

    msg = await context.bot.send_photo(
        chat_id=chat_id,
        photo=photo_file_id,
        caption=caption,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    db.save_active_poll(girl_id, chat_id, msg.message_id)


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_user_allowed(user_id):
        await query.answer("You don't have access.", show_alert=True)
        return

    parts = query.data.split("_")
    if len(parts) != 3:
        await query.answer("Error")
        return

    girl_id = int(parts[1])
    score = int(parts[2])

    girl = db.get_girl(girl_id)
    if not girl:
        await query.answer("Record not found")
        return

    is_new = db.add_vote(girl_id, user_id, score)
    avg, count = db.get_weighted_average(girl_id)

    if is_new:
        await query.answer(f"Your rating: {score}")
    else:
        await query.answer(f"Rating updated: {score}")

    new_caption = (
        f"**Rate: {girl['name']}**\n"
        f"Choose a rating from 1 to 10:\n\n"
        f"Current rating: **{avg}** ({count} votes)"
    )

    try:
        await query.edit_message_caption(
            caption=new_caption,
            reply_markup=_build_vote_keyboard(girl_id),
            parse_mode="Markdown"
        )
    except Exception:
        pass


# ========== Tier List ==========

def _get_tier(score: float) -> str:
    for tier, boundary in TIER_BOUNDARIES.items():
        if score >= boundary:
            return tier
    return "F"


TIER_EMOJI = {
    "S": "[S]", "A": "[A]", "B": "[B]", "C": "[C]", "D": "[D]", "F": "[F]"
}


async def tierlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    if not check_chat(update):
        return

    girls = db.get_all_girls_ranked()
    if not girls:
        await update.message.reply_text("No one here yet. Use /add")
        return

    tiers = {}
    for girl in girls:
        if girl["vote_count"] < MIN_VOTES:
            tier = "?"
        else:
            tier = _get_tier(girl["avg_score"])

        if tier not in tiers:
            tiers[tier] = []
        tiers[tier].append(girl)

    text = "**TIER LIST**\n\n"

    tier_order = ["S", "A", "B", "C", "D", "F", "?"]
    for tier in tier_order:
        if tier not in tiers:
            continue
        emoji = TIER_EMOJI.get(tier, "?")
        text += f"**{emoji} Tier {tier}:**\n"
        for g in tiers[tier]:
            score_str = f"{g['avg_score']:.1f}" if g["vote_count"] >= MIN_VOTES else "N/A"
            text += f"  * {g['name']} -- {score_str} ({g['vote_count']} votes)\n"
        text += "\n"

    buttons = []
    row = []
    for girl in girls:
        row.append(InlineKeyboardButton(
            girl["name"], callback_data=f"show_{girl['id']}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def show_girl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_user_allowed(user_id):
        await query.answer("No access.", show_alert=True)
        return

    girl_id = int(query.data.split("_")[1])

    girl = db.get_girl(girl_id)
    if not girl:
        await query.answer("Not found")
        return

    avg, count = db.get_weighted_average(girl_id)
    tier = _get_tier(avg) if count >= MIN_VOTES else "?"
    emoji = TIER_EMOJI.get(tier, "?")

    caption = (
        f"**{girl['name']}** {emoji} Tier {tier}\n"
        f"Rating: {avg} ({count} votes)\n"
    )
    if girl["contact"]:
        caption += f"Contact: {girl['contact']}\n"

    await query.answer()
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=girl["photo_file_id"],
        caption=caption,
        parse_mode="Markdown"
    )


# ========== Top ==========

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    if not check_chat(update):
        return

    girls = db.get_all_girls_ranked()
    if not girls:
        await update.message.reply_text("No one here yet.")
        return

    ranked = [g for g in girls if g["vote_count"] >= MIN_VOTES]

    if not ranked:
        await update.message.reply_text(f"No entries with {MIN_VOTES}+ votes yet.")
        return

    text = "**TOP 10:**\n\n"
    for i, g in enumerate(ranked[:10], 1):
        text += f"{i}. **{g['name']}** -- {g['avg_score']:.1f} ({g['vote_count']} votes)\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ========== Delete ==========

async def delete_girl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /delete <id>")
        return

    try:
        girl_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID must be a number.")
        return

    girl = db.get_girl(girl_id)
    if not girl:
        await update.message.reply_text("Not found.")
        return

    if girl["submitted_by"] != update.effective_user.id and not _is_admin(update.effective_user.id):
        await update.message.reply_text("You can only delete your own entries.")
        return

    db.delete_girl(girl_id)
    await update.message.reply_text(f"**{girl['name']}** deleted.", parse_mode="Markdown")


# ========== Help ==========

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return

    text = (
        "**Commands:**\n\n"
        "/add - add a girl\n"
        "/tierlist - tier list with photo buttons\n"
        "/top - top 10\n"
        "/delete <id> - delete your entry\n"
        "/cancel - cancel current action\n"
    )

    if _is_admin(update.effective_user.id if update.effective_user else 0):
        text += (
            "\n**Admin Commands:**\n"
            "* /allow <id> [id2 ...] - add to whitelist\n"
            "* /deny <id> [id2 ...] - remove from whitelist\n"
            "* /users - show whitelist\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ========== Handler Setup ==========

def get_add_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            WAITING_PHOTO: [
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(~filters.COMMAND & ~filters.PHOTO, add_photo),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_name),
            ],
            WAITING_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_contact_text),
                CallbackQueryHandler(add_contact_skip, pattern="^skip_contact$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )