import html
import logging

from bs4 import BeautifulSoup
from dataclasses import dataclass
from flask_app import FlaskApp
from limesurvey_handler import LimeSurveyHandler
from survey_data import SurveyData
from config import Config
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler,
    ExtBot,
)

# import your messages dictionaries
from messages_en import MESSAGES as MESSAGES_EN
from messages_de import MESSAGES as MESSAGES_DE

LOGGER = logging.getLogger(__name__)


def prepare_logger():
    """ Setup logger """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )

    """ Set a higher logging level for httpx to avoid all GET and POST requests being logged """
    logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class WebhookUpdate:
    """Simple dataclass to wrap a custom update type"""

    user_id: int
    payload: str


class CustomContext(CallbackContext[ExtBot, dict, dict, dict]):
    """
    Custom CallbackContext class that makes `user_data` available for updates of type
    `WebhookUpdate`.
    """

    @classmethod
    def from_update(
            cls,
            update: object,
            application: "Application",
    ) -> "CustomContext":
        if isinstance(update, WebhookUpdate):
            return cls(application=application, user_id=update.user_id)
        return super().from_update(update, application)


class TelegramBotHandler:

    def __init__(self, config: Config):
        """  set messages to correct dictionary based on language. """
        if config.LANG.lower() == "en":
            self.lang_messages = MESSAGES_EN
        elif config.LANG.lower() == "de":
            self.lang_messages = MESSAGES_DE
        else:
            raise ValueError("Language not supported" + config.LANG)

        """ Set up PTB application and a web application for handling the incoming requests. """
        self.TOKEN = config.TOKEN
        self.BOT_USERNAME = config.BOT_USERNAME
        self.URL = config.URL
        self.PORT = config.PORT
        self.HOST = config.HOST
        self.SURVEY_ID = config.SURVEY_ID
        self.MULTI_VOTE = config.MULTI_VOTE
        self.FREQUENCIES = config.FREQUENCIES
        self.SET_FREQUENCY = config.SET_FREQUENCY

        context_types = ContextTypes(context=CustomContext)

        self.app = Application.builder().token(self.TOKEN).updater(None).context_types(context_types).build()
        self.job_queue = self.app.job_queue
        self.survey_data = SurveyData(int(self.SURVEY_ID), LimeSurveyHandler(config))
        self.questions = self.survey_data.question_list()

        prepare_logger()

    async def help_command(self, update: Update, context: CustomContext):
        """ Display a message with instructions on how to use this bot. """
        text = self.lang_messages["help_info"]
        await update.message.reply_html(text=text)

    async def admin_help_command(self, update: Update, context: CustomContext):
        """ Display a message with instructions on how to use this bot. """
        url = html.escape(f"{self.URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            self.lang_messages["admin_help_info"].format(url=url)
        )
        await update.message.reply_html(text=text)

    async def cancel_command(self, update: Update, context: CustomContext):
        """ Cancels and ends the conversation. """
        user = update.message.from_user
        LOGGER.info("User %s canceled the survey.", user.first_name)
        await update.message.reply_text(self.lang_messages["cancel_msg"])

    async def stop_command(self, update: Update, context: CustomContext):
        """End Conversation by command."""
        await update.message.reply_text(self.lang_messages["stop_msg"])

    async def start_command(self, update: Update, context: CustomContext):
        if self.MULTI_VOTE or 'survey_completed' not in context.user_data or not context.user_data['survey_completed']:
            user = update.effective_user
            self.__initiate_survey_for_user(context)
            await self.__prepare_job_queue(context, update)
            LOGGER.info("User %s started the survey.", user.first_name)

    def __initiate_survey_for_user(self, context: CustomContext):
        context.user_data['sid'] = self.survey_data.sid()
        if 'frequency' not in context.user_data:
            context.user_data['frequency'] = "every_2_seconds"
        self.__reset_current_question(context)

    async def __prepare_job_queue(self, context: CustomContext, update: Update):
        chat_id = update.effective_message.chat_id
        interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        context.user_data['send_confirmation'] = True
        context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))

    @staticmethod
    def __remove_job_if_exists(name: str, context: CustomContext) -> bool:
        """ Remove job with given name. Returns whether job was removed. """
        current_jobs = context.job_queue.get_jobs_by_name(name)
        if not current_jobs:
            return False
        for job in current_jobs:
            job.schedule_removal()
        return True

    @staticmethod
    def __build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    @staticmethod
    async def __send_message(context, chat_id, text, show_image=True, reply_markup=None):
        img_urls, soup = await TextParser.separate_text_and_image(text)
        # Send each image
        if show_image:
            for url in img_urls:
                print(f"Here is picture: '{chat_id}' was {url} ")
                await context.bot.send_photo(chat_id, photo=url)
        try:
            # Send the text part
            await context.bot.send_message(chat_id, text=str(soup), reply_markup=reply_markup)
        except Exception as err:
            print(f"An error occurred in __send_message: {err}")

    async def show_question(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.chat_id

        current_question = self.app.user_data[chat_id]['current_question']
        if current_question < len(self.questions):
            question_data = self.questions[current_question]
            await self.__prepare_and_send_question(context, chat_id, question_data)
        else:
            self.app.user_data[chat_id]['survey_completed'] = True
            await self.__send_message(context, chat_id, self.lang_messages["questions_complete_msg"])
            sid = self.survey_data.sid()
            self.survey_data.save_survey_response(sid, chat_id, self.app.user_data)

    async def show_question_no_image(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.chat_id

        current_question = self.app.user_data[chat_id]['current_question']
        if current_question < len(self.questions):
            question_data = self.questions[current_question]
            await self.__prepare_and_send_question(context, chat_id, question_data, False)
        else:
            self.app.user_data[chat_id]['survey_completed'] = True
            await self.__send_message(context, chat_id, self.lang_messages["questions_complete_msg"])
            sid = self.survey_data.sid()
            self.survey_data.save_survey_response(sid, chat_id, self.app.user_data)

    async def __prepare_and_send_question(self, context, chat_id, question_data, show_image=True):
        question_text = f"{question_data['question']}"
        if 'answeroptions' in question_data and isinstance(question_data['answeroptions'], dict):
            buttons = [InlineKeyboardButton(answer_data['answer'], callback_data=f",{answer_key}")
                       for answer_key, answer_data in question_data['answeroptions'].items()]
            reply_markup = InlineKeyboardMarkup(self.__build_menu(buttons, n_cols=1))
            await self.__send_message(context, chat_id, question_text, show_image, reply_markup=reply_markup)
        else:
            await self.__send_message(context, chat_id, question_text, show_image)

    @staticmethod
    def __set_next_question(context):
        """ Move to the next question"""
        context.user_data['current_question'] += 1

    @staticmethod
    def __reset_current_question(context):
        """ Reset the next question value"""
        context.user_data['current_question'] = 0

    @staticmethod
    def __set_send_confirmation(context, send_confirmation: bool):
        context.user_data['send_confirmation'] = send_confirmation

    async def handle_user_answer(self, update: Update, context: CustomContext) -> None:
        query = update.callback_query
        chat_id = update.effective_message.chat_id

        await self.__show_answer(context, query)

        if context.user_data['send_confirmation']:
            await self.send_confirmation(context, chat_id)
        else:
            self.__set_next_question(context)
            self.__set_send_confirmation(context, True)
            await self.__add_question_to_job_queue(chat_id, context)

    async def __show_answer(self, context, query):
        await query.answer()
        user_answer = query.data.lstrip(',')
        question_data = self.questions[context.user_data['current_question']]
        question_code = question_data['code']
        question_text = f"{question_data['question']}"
        answer_text = TextParser.get_answer_text(question_data, user_answer)

        """ Save user answer into bot.user_data """
        context.user_data[question_code] = user_answer

        confirmed_answer_text = self.lang_messages["answered_msg"].format(answer=answer_text)
        await query.edit_message_text(confirmed_answer_text)

        """ Print the answer to console """
        print(f"Your answer was {answer_text} ")

    async def __add_question_to_job_queue(self, chat_id, context, interval=None, show_image=True):
        self.__remove_job_if_exists(str(chat_id), context)
        if interval is None:
            interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        if show_image:
            context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))
        else:
            context.job_queue.run_once(self.show_question_no_image, interval, chat_id=chat_id, name=str(chat_id))

    async def send_confirmation(self, context: CallbackContext, chat_id: int):
        """ Send the confirmation question to user """
        keyboard = [
            [InlineKeyboardButton(self.lang_messages["yes_msg"], callback_data="_yes")],
            [InlineKeyboardButton(self.lang_messages["no_msg"], callback_data="_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.__send_message(context, chat_id, self.lang_messages["confirmation_msg"], reply_markup=reply_markup)

    async def confirmation_button_click(self, update: Update, context: CustomContext):
        """ Handle users answer to the confirmation question"""
        query = update.callback_query
        selected_option = query.data
        chat_id = update.effective_message.chat_id
        await query.edit_message_text("...")
        if selected_option == "_yes":
            self.__set_next_question(context)
            await self.__add_question_to_job_queue(chat_id, context)
        else:
            self.__set_send_confirmation(context, False)
            await self.__add_question_to_job_queue(chat_id, context, 0, False)

    @staticmethod
    def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f'Update {update} caused error {context.error}')

    async def set_frequency_command(self, update: Update, context: CustomContext) -> int:
        """ Start the conversation to set the frequency. """
        if 'current_question' not in context.user_data or context.user_data['current_question'] >= len(self.questions):
            keyboard = []
            user = update.effective_user
            greet_and_set_frequency_text = self.lang_messages["greet_and_set_frequency"].format(
                username=user.first_name)
            await update.message.reply_text(greet_and_set_frequency_text)

            """ You can add the inline keyboard buttons here"""
            for key, value in self.FREQUENCIES.items():
                button_text = value["text"]
                callback_data = key
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            reply_markup = InlineKeyboardMarkup(keyboard)
            select_frequency_text = self.lang_messages["select_frequency"]
            await update.message.reply_text(select_frequency_text, reply_markup=reply_markup)
            return self.SET_FREQUENCY

        return ConversationHandler.END

    async def handle_frequency_choice(self, update: Update, context: CustomContext) -> int:
        """ Handle the user's choice of frequency. """
        if 'current_question' not in context.user_data or context.user_data['current_question'] >= len(self.questions):
            query = update.callback_query
            await query.answer()

            selected_frequency = query.data
            context.user_data['frequency'] = selected_frequency

            text_to_show = self.FREQUENCIES[selected_frequency]["text"]

            """ reply to the user"""
            frequency_set_confirmation_text = self.lang_messages["frequency_set_confirmation"].format(
                frequency=text_to_show)
            await query.edit_message_text(frequency_set_confirmation_text)
        return ConversationHandler.END

    async def run(self) -> None:
        print('Starting bot...')

        """ Add conversation handler with the states SET_FREQUENCY """
        self.app.add_handler(
            ConversationHandler(
                entry_points=[CommandHandler('setfrequency', self.set_frequency_command)],
                states={
                    self.SET_FREQUENCY: [CallbackQueryHandler(self.handle_frequency_choice)],
                },
                fallbacks=[CommandHandler("cancel", self.cancel_command)],
            )
        )
        """ Register Commands """
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("h", self.admin_help_command))
        """ Register callback query handlers """
        self.app.add_handler(CallbackQueryHandler(self.handle_user_answer, pattern=f"^,"))
        self.app.add_handler(CallbackQueryHandler(self.confirmation_button_click, pattern=f"^_yes|^_no"))

        """ Register Errors """
        self.app.add_error_handler(self.error)

        """ Pass webhook settings to telegram """
        await self.app.bot.set_webhook(url=f"{self.URL}/telegram", allowed_updates=Update.ALL_TYPES)

        flask_app = FlaskApp(self.app)

        """ Run application and webserver together"""
        async with self.app:
            await self.app.start()
            await flask_app.run().serve()
            await self.app.stop()


class TextParser:
    @staticmethod
    async def separate_text_and_image(text):
        # Use BeautifulSoup to parse the text
        soup = BeautifulSoup(text, 'html.parser')
        # Find img tags
        img_tags = soup.find_all('img')
        # Extract the src URLs from the img tags
        img_urls = [img['src'] for img in img_tags if 'src' in img.attrs]
        # Remove img tags from the text
        for img_tag in img_tags:
            img_tag.extract()
        return img_urls, soup

    @staticmethod
    def get_answer_text(question_data: dict, answer_key: str):
        for option_key, option_data in question_data['answeroptions'].items():
            if option_key == answer_key:
                return option_data['answer']
        return None  # Return None if the answer_key is not found
