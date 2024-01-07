import asyncio
from telegram_bot_handler import TelegramBotHandler
from survey_data import SurveyData

class Application:
  def __init__(self):
      # Initialization
      self.telegram_bot_handler = TelegramBotHandler(SurveyData(182213))

  def run(self):
      # Use TelegramBotHandler to run the application
      asyncio.run(self.telegram_bot_handler.run())

