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
    MessageHandler,
    filters,
)
import logging

GENDER, PHOTO, LOCATION, BIO = range(4)
TOKEN: Final = "6410577113:AAGaS3vQaF4GjPssgyrJNYCBUgdPzSC6n28"
BOT_USERNAME: Final = "@Oops_o_bot"

# Define conversation states
ASK_QUESTION = 0

class TelegramBotHandler:

    def __init__(self, survey_data: SurveyData):
        self.app = Application.builder().token(TOKEN).build()
        self.survey_data = survey_data
        self.questions = self.survey_data.get_survey_dict()

        # Enable logging
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        # Set a higher logging level for httpx to avoid all GET and POST requests being logged
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self.logger = logging.getLogger(__name__)


    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(f'Help: Here is some info!')

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        user = update.message.from_user
        self.logger.info("User %s canceled the survey.", user.first_name)
        await update.message.reply_text(
            "Bye! I hope we can talk again some day."
        )

        return ConversationHandler.END

    async def start_command(self, update: Update, context: CallbackContext) -> int:
        user = update.effective_user
        context.user_data['sid'] = self.survey_data.get_survey_id()
        await update.message.reply_text(f"Welcome {user.first_name}! Let's get started with the questions.")

        # sets dict at index to 0
        context.user_data['current_question'] = 0

        return await self.show_question(context, update)

    async def stop_command(self, update: Update, context: CallbackContext) -> int:
        """End Conversation by command."""
        await update.message.reply_text("Okay, bye.")
        return ConversationHandler.END

    async def ask_question(self, update: Update, context: CallbackContext) -> int:
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
        return 'I dont understand what you said'

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    def run(self):
        print('Starting bot...')

        # Add conversation handler with the states ASK_QUESTIONO
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                ASK_QUESTION: [CallbackQueryHandler(self.ask_question, pattern=f"^,")],
            },
            fallbacks=[CommandHandler("stop", self.stop_command),
                        CommandHandler("cancel", self.cancel_command)],
        )

        self.app.add_handler(conv_handler)

        # Commands
        #self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))

        # Messages
        self.app.add_handler(MessageHandler(filters.TEXT, self.handle_message))

        # Errors
        self.app.add_error_handler(self.error)

        # Poll the bot
        print('Polling...')
        # Run the bot until the user presses Ctrl-C
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
