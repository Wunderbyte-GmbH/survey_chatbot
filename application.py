import asyncio
from telegram_bot_handler import TelegramBotHandler
from config import Config


class Application:
    def __init__(self):
        # Initialization
        config = Config()
        self.telegram_bot_handler = TelegramBotHandler(config)

    def run(self):
        # Use TelegramBotHandler to run the application
        asyncio.run(self.telegram_bot_handler.run())
