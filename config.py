import json
import os
from typing import Final


class Config:

    def __init__(self):
        """ Read constants from environment variables """
        self.HEADERS = json.loads(Config.get_env_value("HEADERS"))
        self.API_URL = Config.get_env_value("API_URL")
        self.LOGIN = Config.get_env_value("LOGIN")
        self.PASSWORD = Config.get_env_value("PASSWORD")

        self.TOKEN: Final = Config.get_env_value("TOKEN")
        self.BOT_USERNAME: Final = Config.get_env_value("BOT_USERNAME")
        self.URL: Final = Config.get_env_value("URL")
        self.PORT: Final = int(Config.get_env_value("PORT"))
        self.HOST: Final = Config.get_env_value("HOST")
        self.SURVEY_ID: Final = int(Config.get_env_value("SURVEY_ID"))
        self.FREQUENCIES = {
        "once_a_day": {"seconds": 24 * 60 * 60, "text": "Once a day"},
        "twice_a_day": {"seconds": 12 * 60 * 60, "text": "Twice a day"},
        "twelve_a_day": {"seconds": 2 * 60 * 60, "text": "Twelve a day"},
        "once_a_month": {"seconds": 30 * 24 * 60 * 60, "text": "Once a month"},
        "every_2_seconds": {"seconds": 2, "text": "Every 2 seconds"},
        "every_10_seconds": {"seconds": 10, "text": "Every 10 seconds"},
        # approximating a month to 30 days here; this would need adjusting for different month lengths
    }
        """ Define conversation states """
        self.SET_FREQUENCY: Final = 1

    @staticmethod
    def get_env_value(key):
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"{key} environment variable is not set.")
        return value
