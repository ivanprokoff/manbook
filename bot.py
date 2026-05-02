import logging
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler
)
from config import BOT_TOKEN, PROXY_URL
import database as db
from handlers import (
    start, help_cmd, tierlist, top, delete_girl_cmd,
    vote_callback, show_girl_callback, get_add_conversation_handler,
    myid, allow_user, deny_user, list_users
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    db.init_db()

    builder = ApplicationBuilder().token(BOT_TOKEN)

    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
        logger.info(f"Using proxy: {PROXY_URL}")

    app = builder.build()

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("tierlist", tierlist))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("delete", delete_girl_cmd))
    app.add_handler(CommandHandler("myid", myid))

    # Админ-команды
    app.add_handler(CommandHandler("allow", allow_user))
    app.add_handler(CommandHandler("deny", deny_user))
    app.add_handler(CommandHandler("users", list_users))

    # Conversation для добавления
    app.add_handler(get_add_conversation_handler())

    # Callback хендлеры
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(show_girl_callback, pattern=r"^show_\d+$"))

    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()