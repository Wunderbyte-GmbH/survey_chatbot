import os
from dotenv import load_dotenv
import html
from dataclasses import dataclass
from http import HTTPStatus

import uvicorn
from asgiref.wsgi import WsgiToAsgi
from flask import Flask, Response, abort, make_response, request

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

# Load environment variables from the .env file
load_dotenv()

# Read constants from environment variables
TOKEN: Final = os.getenv("TOKEN")
BOT_USERNAME: Final = os.getenv("BOT_USERNAME")
URL: Final = os.getenv("URL")
PORT: Final = int(os.getenv("PORT", 8000))
HOST: Final = os.getenv("HOST")

# Define conversation states
ASK_QUESTION = 0

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

    def __init__(self, survey_data: SurveyData):
        """Set up PTB application and a web application for handling the incoming requests."""
        context_types = ContextTypes(context=CustomContext)
        # Here we set updater to None because we want our custom webhook server to handle the updates
        # and hence we don't need an Updater instance
        self.app = (
            Application.builder().token(TOKEN).updater(None).context_types(context_types).build()
        )
        #self.app = Application.builder().token(TOKEN).build()
        self.survey_data = survey_data
        self.questions = self.survey_data.get_survey_dict()

        # Enable logging
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        # Set a higher logging level for httpx to avoid all GET and POST requests being logged
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self.logger = logging.getLogger(__name__)


    async def help_command(self, update: Update, context: CustomContext)-> int:
        """Display a message with instructions on how to use this bot."""
        payload_url = html.escape(f"{URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            f"/help: Show help info\n"
            f"/start: start the Survey Bot\n"
            f"/cancel: Cancel the survey\n"
        )
        await update.message.reply_html(text=text)

    async def admin_help_command(self, update: Update, context: CustomContext)-> int:
        """Display a message with instructions on how to use this bot."""
        payload_url = html.escape(f"{URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            f"To check if the bot is still running, call <code>{URL}/healthcheck</code>.\n\n"
        )
        await update.message.reply_html(text=text)

    async def cancel_command(self, update: Update, context: CustomContext) -> int:
        """Cancels and ends the conversation."""
        user = update.message.from_user
        self.logger.info("User %s canceled the survey.", user.first_name)
        await update.message.reply_text(
            "Bye! I hope we can talk again some day."
        )

        return ConversationHandler.END

    async def start_command(self, update: Update, context: CustomContext) -> int:
        user = update.effective_user
        context.user_data['sid'] = self.survey_data.get_survey_id()
        await update.message.reply_text(f"Welcome {user.first_name}! Let's get started with the questions.")

        # sets dict at index to 0
        context.user_data['current_question'] = 0

        return await self.show_question(context, update)

    async def stop_command(self, update: Update, context: CustomContext) -> int:
        """End Conversation by command."""
        await update.message.reply_text("Okay, bye.")
        return ConversationHandler.END

    async def ask_question(self, update: Update, context: CustomContext) -> int:
        await self.show_answer(context, update)

        # Move to the next question
        context.user_data['current_question'] += 1

        return await self.show_question(context, update)

    async def show_question(self, context, update):
        # If it is not the first question
        if context.user_data['current_question'] != 0:
            query = update.callback_query

        if context.user_data['current_question'] < len(self.questions):
            question_data = self.questions[context.user_data['current_question']]
            question_text = f"{question_data['question']}"

            if 'answeroptions' in question_data and isinstance(question_data['answeroptions'], dict):
                buttons = [
                    InlineKeyboardButton(answer_data['answer'], callback_data=f",{answer_key}")
                    for answer_key, answer_data in question_data['answeroptions'].items()
                ]
                reply_markup = InlineKeyboardMarkup(self.build_menu(buttons, n_cols=1))
                if context.user_data['current_question'] == 0:
                    await update.message.reply_text(question_text, reply_markup=reply_markup)
                else:
                    await query.message.reply_text(question_text, reply_markup=reply_markup)
                return ASK_QUESTION
            else:
                await update.message.reply_text(question_text)

        else:
            if context.user_data['current_question'] == 0:
                await update.message.reply_text("All questions have been asked. Thank you for your responses!")
            else:
                await query.message.reply_text("All questions have been asked. Thank you for your responses!")

            sid= self.survey_data.get_survey_id()
            self.survey_data.save_survey_response(sid, context.user_data)

            return ConversationHandler.END

    async def show_answer(self, context, update):
        query = update.callback_query
        await query.answer()
        user_answer = query.data.lstrip(',')
        # Save user answer if needed
        question_data = self.questions[context.user_data['current_question']]
        question_code = question_data['code']
        question_text = f"{question_data['question']}"
        # Save user answer into bot.user_data
        context.user_data[question_code] = user_answer
        answer_text = self.get_answer_text(question_data, user_answer)
        await query.edit_message_text(
            f"Your answer to question: '{question_text}' was: {answer_text}")
        # Print the answer to console
        print(f"Your answer to question: '{question_text}' was {answer_text} ")

    def get_answer_text(self, question_data, answer_key):
        for option_key, option_data in question_data['answeroptions'].items():
            if option_key == answer_key:
                return option_data['answer']
        return None  # Return None if the answer_key is not found

    def build_menu(self, buttons, n_cols, header_buttons=None, footer_buttons=None):
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    def handle_response(self, text: str) -> str:
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

    def error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f'Update {update} caused error {context.error}')

    async def run(self)-> None:
        print('Starting bot...')

        # Add conversation handler with the states ASK_QUESTION
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                ASK_QUESTION: [CallbackQueryHandler(self.ask_question, pattern=f"^,")],
            },
            fallbacks=[CommandHandler("stop", self.stop_command)],
        )

        self.app.add_handler(conv_handler)

        # Commands
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("h", self.admin_help_command))

        # Messages
        self.app.add_handler(MessageHandler(filters.TEXT, self.handle_message))

        # Errors
        self.app.add_error_handler(self.error)

        # Pass webhook settings to telegram
        await self.app.bot.set_webhook(url=f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)

        # Set up webserver
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

        # Poll the bot
        print('Polling...')

        webserver = uvicorn.Server(
            config=uvicorn.Config(
                app=WsgiToAsgi(flask_app),
                port=PORT,
                use_colors=False,
                host="127.0.0.1",
            )
        )

        # Run application and webserver together
        async with self.app:
            await self.app.start()
            await webserver.serve()
            await self.app.stop()
