import logging
from telegram import Update
from telegram.ext import ContextTypes
from services.vector_search import SearchService

logger = logging.getLogger(__name__)


class GroupMessageHandler:
    def __init__(self, search_service: SearchService) -> None:
        self._search_service = search_service

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message or not message.text:
            return

        if message.chat.type not in ("group", "supergroup"):
            return

        logger.info(
            "Incoming message | user: %s | chat: %s | text: %.80s",
            message.from_user.full_name,
            message.chat.title,
            message.text,
        )

        result = self._search_service.search(message.text)
        if result:
            await self._send_long_message(message, result.content)
        else:
            await message.reply_text(
                "❌ Bu savolga javob topilmadi.\nIltimos, adminga murojaat qiling. 🙏"
            )

    async def _send_long_message(self, message, text: str) -> None:
        chunk_size = 4000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        for chunk in chunks:
            await message.reply_text(chunk)