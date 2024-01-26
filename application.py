import asyncio
from telegram_bot_handler import TelegramBotHandler


class Application:
    def __init__(self):
        # Initialization
        self.telegram_bot_handler = TelegramBotHandler()

    def run(self):
        # Use TelegramBotHandler to run the application
        asyncio.run(self.telegram_bot_handler.run())
