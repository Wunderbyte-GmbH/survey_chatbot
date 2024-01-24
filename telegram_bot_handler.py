import os
import html
from dotenv import load_dotenv
from dataclasses import dataclass
from http import HTTPStatus

import uvicorn
from asgiref.wsgi import WsgiToAsgi
from flask import Flask, Response, make_response, request

from typing import Final
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

""" Load environment variables from the .env file """
load_dotenv()

""" Read constants from environment variables """
TOKEN: Final = os.getenv("TOKEN")
BOT_USERNAME: Final = os.getenv("BOT_USERNAME")
URL: Final = os.getenv("URL")
PORT: Final = int(os.getenv("PORT"))
HOST: Final = os.getenv("HOST")

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
        # approximating a month to 30 days here; this would need adjusting for different month lengths
    }

    def __init__(self, survey_data: SurveyData):
        """ Set up PTB application and a web application for handling the incoming requests. """

        context_types = ContextTypes(context=CustomContext)
        self.app = Application.builder().token(TOKEN).updater(None).context_types(context_types).build()
        self.job_queue = self.app.job_queue
        self.survey_data = survey_data
        self.questions = self.survey_data.get_survey_dict()

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
        payload_url = html.escape(f"{URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            f"To check if the bot is still running, call <code>{URL}/healthcheck</code>.\n\n"
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
        user = update.effective_user
        context.user_data['sid'] = self.survey_data.get_survey_id()
        if 'frequency' not in context.user_data:
            context.user_data['frequency'] = "every_2_seconds"
        await update.message.reply_text(f"Welcome {user.first_name}! Let's get started with the questions.")

        """ sets dict at index to 0 """
        context.user_data['current_question'] = 0
        """ Sets up a job to ask question every x seconds."""
        chat_id = update.effective_message.chat_id
        interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        context.user_data['send_confirmation'] = True
        context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))

    @staticmethod
    def remove_job_if_exists(name: str, context: CustomContext) -> bool:
        """ Remove job with given name. Returns whether job was removed. """
        current_jobs = context.job_queue.get_jobs_by_name(name)
        if not current_jobs:
            return False
        for job in current_jobs:
            job.schedule_removal()
        return True

    @staticmethod
    def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    async def show_question(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job

        #print(f"---:'{context.job}'")

        """ Show the question."""
        current_question = self.app.user_data[job.chat_id]['current_question']
        """ We presume that 'current_question', 'questions', etc. are set in job.context"""
        if current_question < len(self.questions):
            question_data = self.questions[current_question]
            question_text = f"{question_data['question']}"

            if 'answeroptions' in question_data and isinstance(question_data['answeroptions'], dict):
                buttons = [
                    InlineKeyboardButton(answer_data['answer'], callback_data=f",{answer_key}")
                    for answer_key, answer_data in question_data['answeroptions'].items()
                ]
                reply_markup = InlineKeyboardMarkup(self.build_menu(buttons, n_cols=1))

                await context.bot.send_message(
                    job.chat_id,
                    text=question_text,
                    reply_markup=reply_markup
                )

            else:
                await context.bot.send_message(job.chat_id, text=question_text)

        else:
            await context.bot.send_message(
                job.chat_id, text="All questions have been asked. Thank you for your responses!"
            )

            sid = self.survey_data.get_survey_id()
            self.survey_data.save_survey_response(sid, self.app.user_data)

    async def show_answer(self, update: Update, context: CustomContext) -> None:
        query = update.callback_query
        await query.answer()
        user_answer = query.data.lstrip(',')
        chat_id = update.effective_message.chat_id

        """ Save user answer if needed """
        question_data = self.questions[context.user_data['current_question']]
        question_code = question_data['code']
        question_text = f"{question_data['question']}"

        """ Save user answer into bot.user_data """
        context.user_data[question_code] = user_answer

        answer_text = self.get_answer_text(question_data, user_answer)
        await query.edit_message_text(
            f"Your answer to question: '{question_text}' was: {answer_text}")

        """ Print the answer to console """
        print(f"Your answer to question: '{question_text}' was {answer_text} ")
        if context.user_data['send_confirmation']:
            await self.send_confirmation(context, chat_id)
        else:
            context.user_data['send_confirmation'] = True
            context.user_data['current_question'] += 1
            self.remove_job_if_exists(str(chat_id), context)
            interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
            context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))

    @staticmethod
    async def send_confirmation(context: CallbackContext, chat_id: int):
        """ Define the question and possible answers """
        question_text = "Are you sure about your answer?"
        """ You can customize the inline keyboard buttons here """
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data="_yes")],
            [InlineKeyboardButton("No", callback_data="_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        """ Send the question with inline keyboard to the user"""
        await context.bot.send_message(chat_id=chat_id, text=question_text, reply_markup=reply_markup)

    async def confirmation_button_click(self, update: Update, context: CustomContext):
        query = update.callback_query
        selected_option = query.data
        chat_id = update.effective_message.chat_id
        await query.edit_message_text("...")
        if selected_option == "_yes":
            """ Move to the next question"""
            context.user_data['current_question'] += 1

            self.remove_job_if_exists(str(chat_id), context)
            interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
            """ Create a job and send a question to the user"""
            context.job_queue.run_once(self.show_question, interval, chat_id=chat_id)

        else:
            context.user_data['send_confirmation'] = False
            context.job_queue.run_once(self.show_question, 0, chat_id=chat_id)

    @staticmethod
    def get_answer_text(question_data: dict, answer_key: str):
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

    @staticmethod
    async def set_frequency_command(update: Update, context: CustomContext) -> int:
        """ Start the conversation to set the frequency. """
        user = update.effective_user
        await update.message.reply_text(f"Hello {user.first_name}! Let's set the frequency.")

        """ You can customize the inline keyboard buttons here"""
        keyboard = [
            [InlineKeyboardButton("Once a day", callback_data="once_a_day")],
            [InlineKeyboardButton("Twice a day", callback_data="twice_a_day")],
            [InlineKeyboardButton("Twelfth a day", callback_data="twelve_a_day")],
            [InlineKeyboardButton("Once a month", callback_data="once_a_month")],
            [InlineKeyboardButton("Every 10 seconds", callback_data="every_10_seconds")],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select the frequency:", reply_markup=reply_markup)

        return SET_FREQUENCY

    async def handle_frequency_choice(self, update: Update, context: CustomContext) -> int:
        """ Handle the user's choice of frequency. """
        query = update.callback_query
        await query.answer()

        selected_frequency = query.data
        context.user_data['frequency'] = selected_frequency

        text_to_show = self.FREQUENCIES[selected_frequency]["text"]
        interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]

        """ reply to the user"""
        await query.edit_message_text(text=f"Frequency set to: {text_to_show}")
        return ConversationHandler.END

    def get_frequency_text(self, freq):
        return self.FREQUENCY_TEXTS.get(freq, "")

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
        """ Commands """
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("h", self.admin_help_command))
        """ Register the callback query handler """
        self.app.add_handler(CallbackQueryHandler(self.show_answer, pattern=f"^,"))
        self.app.add_handler(CallbackQueryHandler(self.confirmation_button_click, pattern=f"^_yes|^_no"))

        """ Messages """
        self.app.add_handler(MessageHandler(filters.TEXT, self.handle_message))

        """ Errors """
        self.app.add_error_handler(self.error)

        """ Pass webhook settings to telegram """
        await self.app.bot.set_webhook(url=f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)

        """ Set up webserver """
        flask_app = Flask(__name__)

        @flask_app.post("/telegram")  # type: ignore[misc]
        async def telegram() -> Response:
            """Handle incoming Telegram updates by putting them into the `update_queue`"""
            await self.app.update_queue.put(Update.de_json(data=request.json, bot=self.app.bot))
            return Response(status=HTTPStatus.OK)

        @flask_app.get("/healthcheck")  # type: ignore[misc]
        async def health() -> Response:
            """For the health endpoint, reply with a simple plain text message."""
            response = make_response("The bot is still running fine :)", HTTPStatus.OK)
            response.mimetype = "text/plain"
            return response

        print('Running...')

        webserver = uvicorn.Server(
            config=uvicorn.Config(
                app=WsgiToAsgi(flask_app),
                port=PORT,
                use_colors=False,
                host="127.0.0.1",
            )
        )

        """ Run application and webserver together"""
        async with self.app:
            await self.app.start()
            await webserver.serve()
            await self.app.stop()
