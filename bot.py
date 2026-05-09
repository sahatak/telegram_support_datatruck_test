import logging

from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.ext import MessageHandler as TGMessageHandler
from telegram.ext import filters

from config import config
from handlers.message_handler import GroupMessageHandler
from services.vector_search import SearchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def start(update: Update, context) -> None:
    await update.message.reply_text("Salom! Men support botman.")


def main() -> None:
    config.validate()

    search_service = SearchService(
        supabase_url=config.SUPABASE_URL,
        supabase_key=config.SUPABASE_KEY,
        table=config.VECTOR_TABLE,
        content_column=config.CONTENT_COLUMN,
    )

    message_handler = GroupMessageHandler(search_service=search_service)

    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        TGMessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle)
    )

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
