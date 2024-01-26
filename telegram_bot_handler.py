import os
import html
from dataclasses import dataclass

from typing import Final

from flask_app import FlaskApp
from survey_data import SurveyData
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler,
    ExtBot,
    MessageHandler,
    filters,
)
import logging


def get_env_value(key):
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"{key} environment variable is not set.")
    return value


""" Read constants from environment variables """
TOKEN: Final = get_env_value("TOKEN")
BOT_USERNAME: Final = get_env_value("BOT_USERNAME")
URL: Final = get_env_value("URL")
PORT: Final = int(get_env_value("PORT"))
HOST: Final = get_env_value("HOST")
SURVEY_ID: Final = int(get_env_value("SURVEY_ID"))

""" Define conversation states """
ASK_QUESTION = 0
SET_FREQUENCY = 1


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
    FREQUENCIES = {
        "once_a_day": {"seconds": 24 * 60 * 60, "text": "Once a day"},
        "twice_a_day": {"seconds": 12 * 60 * 60, "text": "Twice a day"},
        "twelve_a_day": {"seconds": 2 * 60 * 60, "text": "Twelve a day"},
        "once_a_month": {"seconds": 30 * 24 * 60 * 60, "text": "Once a month"},
        "every_2_seconds": {"seconds": 2, "text": "Every 2 seconds"},
        "every_10_seconds": {"seconds": 10, "text": "Every 10 seconds"},
        # approximating a month to 30 days here; this would need adjusting for different month lengths
    }

    def __init__(self):
        """ Set up PTB application and a web application for handling the incoming requests. """

        context_types = ContextTypes(context=CustomContext)
        # Read values from environment variables
        self.app = Application.builder().token(TOKEN).updater(None).context_types(context_types).build()
        self.job_queue = self.app.job_queue
        self.survey_data = SurveyData(int(SURVEY_ID))
        self.questions = self.survey_data.question_list()

        """ Enable logging """
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        """ Set a higher logging level for httpx to avoid all GET and POST requests being logged """
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self.logger = logging.getLogger(__name__)

    @staticmethod
    async def help_command(update: Update, context: CustomContext):
        """ Display a message with instructions on how to use this bot. """
        text = (
            f"/help: Show help info\n"
            f"/start: Start the Survey Bot\n"
            f"/setfrequency: Set frequency\n"
            f"/cancel: Cancel the survey\n"
        )
        await update.message.reply_html(text=text)

    @staticmethod
    async def admin_help_command(update: Update, context: CustomContext):
        """ Display a message with instructions on how to use this bot. """
        url = html.escape(f"{URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            f"To check if the bot is still running, call <code>{url}/healthcheck</code>.\n\n"
        )
        await update.message.reply_html(text=text)

    async def cancel_command(self, update: Update, context: CustomContext):
        """ Cancels and ends the conversation. """
        user = update.message.from_user
        self.logger.info("User %s canceled the survey.", user.first_name)
        await update.message.reply_text(
            "Bye! I hope we can talk again some day."
        )

    @staticmethod
    async def stop_command(update: Update, context: CustomContext):
        """End Conversation by command."""
        await update.message.reply_text("Okay, bye.")

    async def start_command(self, update: Update, context: CustomContext):
        if 'survey_completed' not in context.user_data or not context.user_data['survey_completed']:
            user = update.effective_user
            self.__initiate_survey_for_user(context)
            await self.__prepare_job_queue(context, update)
            await update.message.reply_text(f"Welcome {user.first_name}! Let's get started with the questions.")

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
    async def __send_message(context, chat_id, text, reply_markup=None):
        await context.bot.send_message(chat_id, text=text, reply_markup=reply_markup)

    async def show_question(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.chat_id
        # print(f"---:'{context.job}'")

        current_question = self.app.user_data[chat_id]['current_question']
        if current_question < len(self.questions):
            question_data = self.questions[current_question]
            await self.__prepare_and_send_question(context, chat_id, question_data)
        else:
            self.app.user_data[chat_id]['survey_completed'] = True
            await self.__send_message(context, chat_id,
                                      "All questions have been asked. Thank you for your responses!")
            sid = self.survey_data.sid()
            self.survey_data.save_survey_response(sid, self.app.user_data)

    async def __prepare_and_send_question(self, context, chat_id, question_data):
        question_text = f"{question_data['question']}"
        if 'answeroptions' in question_data and isinstance(question_data['answeroptions'], dict):
            buttons = [InlineKeyboardButton(answer_data['answer'], callback_data=f",{answer_key}")
                       for answer_key, answer_data in question_data['answeroptions'].items()]
            reply_markup = InlineKeyboardMarkup(self.__build_menu(buttons, n_cols=1))
            await self.__send_message(context, chat_id, question_text, reply_markup=reply_markup)
        else:
            await self.__send_message(context, chat_id, question_text)

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
        answer_text = self.__get_answer_text(question_data, user_answer)

        """ Save user answer into bot.user_data """
        context.user_data[question_code] = user_answer

        await query.edit_message_text(
            f"Your answer to question: '{question_text}' was: {answer_text}")
        """ Print the answer to console """
        print(f"Your answer to question: '{question_text}' was {answer_text} ")

    async def __add_question_to_job_queue(self, chat_id, context, interval=None):
        self.__remove_job_if_exists(str(chat_id), context)
        if interval is None:
            interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))

    async def send_confirmation(self, context: CallbackContext, chat_id: int):
        """ Send the confirmation question to user """
        question_text = "Are you sure about your answer?"
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data="_yes")],
            [InlineKeyboardButton("No", callback_data="_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.__send_message(context, chat_id, question_text, reply_markup=reply_markup)

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
            await self.__add_question_to_job_queue(chat_id, context, 0)

    @staticmethod
    def __get_answer_text(question_data: dict, answer_key: str):
        for option_key, option_data in question_data['answeroptions'].items():
            if option_key == answer_key:
                return option_data['answer']
        return None  # Return None if the answer_key is not found

    @staticmethod
    def handle_response(text: str) -> str:
        processed: str = text.lower()
        if 'hello' in processed:
            return 'Hey there!'
        if 'how are you' in processed:
            return 'I am good!'

    async def handle_message(self, update: Update, context: CustomContext):
        message_type: str = update.message.chat.type
        text: str = update.message.text

        print(f'User ({update.message.chat.id}) in {message_type}: "{text}"')
        if message_type == 'group':
            if BOT_USERNAME in text:
                new_text: str = text.replace(BOT_USERNAME, '')
                response: str = self.handle_response(new_text)
            else:
                return
        else:
            response: str = self.handle_response(text)
        print('Bot:', response)
        await update.message.reply_text(response)

    @staticmethod
    def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f'Update {update} caused error {context.error}')

    async def set_frequency_command(self, update: Update, context: CustomContext) -> int:
        """ Start the conversation to set the frequency. """
        if 'current_question' not in context.user_data or context.user_data['current_question'] >= len(self.questions):
            keyboard = []
            user = update.effective_user
            await update.message.reply_text(f"Hello {user.first_name}! Let's set the frequency.")

            """ You can add the inline keyboard buttons here"""
            for key, value in self.FREQUENCIES.items():
                button_text = value["text"]
                callback_data = key
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Select the frequency:", reply_markup=reply_markup)
            return SET_FREQUENCY

        return ConversationHandler.END

    async def handle_frequency_choice(self, update: Update, context: CustomContext) -> int:
        """ Handle the user's choice of frequency. """
        if 'current_question' not in context.user_data or context.user_data['current_question'] >= len(self.questions):
            query = update.callback_query
            await query.answer()

            selected_frequency = query.data
            context.user_data['frequency'] = selected_frequency

            text_to_show = self.FREQUENCIES[selected_frequency]["text"]
            # interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]

            """ reply to the user"""
            await query.edit_message_text(text=f"Frequency set to: {text_to_show}")
        return ConversationHandler.END

    async def run(self) -> None:
        print('Starting bot...')

        """ Add conversation handler with the states SET_FREQUENCY """
        self.app.add_handler(
            ConversationHandler(
                entry_points=[CommandHandler('setfrequency', self.set_frequency_command)],
                states={
                    SET_FREQUENCY: [CallbackQueryHandler(self.handle_frequency_choice)],
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

        """ Register Messages """
        # self.app.add_handler(MessageHandler(filters.TEXT, self.handle_message))

        """ Register Errors """
        self.app.add_error_handler(self.error)

        """ Pass webhook settings to telegram """
        await self.app.bot.set_webhook(url=f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)

        flask_app = FlaskApp(self.app)

        """ Run application and webserver together"""
        async with self.app:
            await self.app.start()
            await flask_app.run().serve()
            await self.app.stop()
