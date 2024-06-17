import hashlib
import html
import logging

from bs4 import BeautifulSoup
from dataclasses import dataclass
from flask_app import FlaskApp
from limesurvey_handler import LimeSurveyHandler
from survey_data import SurveyData
from config import Config
from buildAddressDataset import AddressDownloader
from trie import Trie

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InlineQueryResultArticle, \
    InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler,
    ExtBot, InlineQueryHandler,
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
        """
        Constructor method where the bot's configurations are instantiated based on the given config.
        The method also includes setting up the survey data, building the web application, and preparing
        the address downloader and logger.
        """
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
        self.address_downloader = AddressDownloader()
        self.trie = Trie()
        for address in self.address_downloader.get_addresses():
            self.trie.insert(address)
        prepare_logger()

    async def help_command(self, update: Update, context: CustomContext):
        """
        Method that handles the '/help' command from users. When invoked, it displays an informative message
        on how to use this bot.
        """
        text = self.lang_messages["help_info"]
        await update.message.reply_html(text=text)

    async def admin_help_command(self, update: Update, context: CustomContext):
        """
        Method that handles the admin help command. Upon invocation, it displays an informative message to help admin
        better understand how to use the application interface.
        """
        url = html.escape(f"{self.URL}/submitpayload?user_id=<your user id>&payload=<payload>")
        text = (
            self.lang_messages["admin_help_info"].format(url=url)
        )
        await update.message.reply_html(text=text)

    async def cancel_command(self, update: Update, context: CustomContext):
        """
        Method that handles the '/cancel' command. When a user invokes this, it cancels any active survey and logs
        this event.
        """
        user = update.message.from_user
        LOGGER.info("User %s canceled the survey.", user.first_name)
        await update.message.reply_text(self.lang_messages["cancel_msg"])

    async def stop_command(self, update: Update, context: CustomContext):
        """
        Method to handle the '/stop' command. When a user invokes this, it sends a stop message to the user.
        """
        await update.message.reply_text(self.lang_messages["stop_msg"])

    async def start_command(self, update: Update, context: CustomContext):
        """
        Method that handles the '/start' command. This initializes the survey for the user and prepares the bot's job queue.
        """
        if self.MULTI_VOTE or 'survey_completed' not in context.user_data or not context.user_data['survey_completed']:
            user = update.effective_user
            self.__initiate_survey_for_user(context)
            await self.__prepare_job_queue(context, update)
            LOGGER.info("User %s started the survey.", user.first_name)

    def __initiate_survey_for_user(self, context: CustomContext):
        """
        Private method to initialize the suvey for a user in the provided context. If the user has not set a frequency for
        the survey, it defaults to 'every_2_seconds'.
        """
        context.user_data['sid'] = self.survey_data.sid()
        if 'frequency' not in context.user_data:
            context.user_data['frequency'] = "every_2_seconds"
        self.__reset_current_question(context)

    async def __prepare_job_queue(self, context: CustomContext, update: Update):
        """
        Private async method to prepare the job queue by setting the required parameters needed to show the questions
        in the provided interval extracted based on user's frequency option.
        """
        chat_id = update.effective_message.chat_id
        interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        context.user_data['send_confirmation'] = True
        context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))

    @staticmethod
    def __remove_job_if_exists(name: str, context: CustomContext) -> bool:
        """
        Static method to remove a job from the job queue matching a provided name. If such a job exists, it is removed
        from the schedule and returns True. If it does not exist, it simply returns False.
        """
        current_jobs = context.job_queue.get_jobs_by_name(name)
        if not current_jobs:
            return False
        for job in current_jobs:
            job.schedule_removal()
        return True

    @staticmethod
    def __build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
        """
        This method builds menu for InlineKeyboardMarkup.

        :return: List of buttons
        """
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    @staticmethod
    async def __send_message(context, chat_id, text, show_image=True, reply_markup=None):
        """
        method for sending a message that may include text and image.
        :param context: Context containing information to be sent.
        :param chat_id: Chat ID where the data to be sent.
        :param text: Message text or content to be sent.
        :param show_image: A boolean parameter to control the content of the message,
                           if True, image will be included in the message.
                           Default value is True.
        :param reply_markup: Additional options for the message like custom keyboard.
        """
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
        """
        method for progressing in the survey by showing the next question.
        :param context: Context containing survey details and user data.
        """
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
        """
        method for progressing in the survey by showing the next question,
        but without showing the image even if it's included in the question.
        :param context: Context containing survey details and user data.
        """
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
        """
        This method prepare_and_send_question.

        Any question that does not have answeroptions, is considered as a question about address which is and inline
        query.

        """
        question_text = f"{question_data['question']}"
        if 'answeroptions' in question_data and isinstance(question_data['answeroptions'], dict) and question_data['answeroptions']:
            buttons = [InlineKeyboardButton(answer_data['answer'], callback_data=f",{answer_key}")
                       for answer_key, answer_data in question_data['answeroptions'].items()]
            reply_markup = InlineKeyboardMarkup(self.__build_menu(buttons, n_cols=1))
            await self.__send_message(context, chat_id, question_text, show_image, reply_markup=reply_markup)
        else:
            """Send a message with a switch inline query button"""
            button = InlineKeyboardButton(
                self.lang_messages["search_msg"],
                switch_inline_query_current_chat=""
            )
            reply_markup = InlineKeyboardMarkup([[button]])
            question_text = f"{question_text}"
            await self.__send_message(context, chat_id, question_text, show_image,reply_markup=reply_markup)

    @staticmethod
    def __set_next_question(context):
        """
        This method increments the value of 'current_question' in context.user_data by 1 to move to the next question.
        :param context: Context containing user data.
        """
        context.user_data['current_question'] += 1

    @staticmethod
    def __reset_current_question(context):
        """
        This method resets the value of 'current_question' in context.user_data to 0.
        :param context: Context containing user data.
        """
        context.user_data['current_question'] = 0

    @staticmethod
    def __set_send_confirmation(context, send_confirmation: bool):
        """
        This method sets the value of 'send_confirmation' in context.user_data.
        :param context: Context containing user data.
        :param send_confirmation: Boolean value to set for 'send_confirmation'.
        """
        context.user_data['send_confirmation'] = send_confirmation

    async def handle_user_answer(self, update: Update, context: CustomContext) -> None:
        """
        This method handles user answers, shows the answer, sends confirmation if 'send_confirmation' is True, sets the next question,
        and adds the question to the job queue.
        :param update: Current update instance.
        :param context: Context containing user data.
        """
        query = update.callback_query
        chat_id = query.from_user.id

        await self.__show_answer(context, query)

        if context.user_data['send_confirmation']:
            await self.send_confirmation(context, chat_id)
        else:
            self.__set_next_question(context)
            self.__set_send_confirmation(context, True)
            await self.__add_question_to_job_queue(chat_id, context)

    async def __show_answer(self, context, query):
        """
        This method displays user's answer, saves user answer into bot.user_data, and prints the answer to console.
        :param context: Context containing user data.
        :param query: Current query.
        """
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
        """
        This method adds a question to the job queue.
        :param chat_id: The id of the chat.
        :param context: The context of the chat.
        :param interval: The interval at which to show the question.
        :param show_image: A boolean indicating whether to show an image.
        """
        self.__remove_job_if_exists(str(chat_id), context)
        if interval is None:
            interval = self.FREQUENCIES[context.user_data['frequency']]["seconds"]
        if show_image:
            context.job_queue.run_once(self.show_question, interval, chat_id=chat_id, name=str(chat_id))
        else:
            context.job_queue.run_once(self.show_question_no_image, interval, chat_id=chat_id, name=str(chat_id))

    async def send_confirmation(self, context: CallbackContext, chat_id: int):
        """
        This method sends a confirmation question to the user.
        :param context: The context of the chat.
        :param chat_id: The id of the chat.
        """
        keyboard = [
            [InlineKeyboardButton(self.lang_messages["yes_msg"], callback_data="_yes")],
            [InlineKeyboardButton(self.lang_messages["no_msg"], callback_data="_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.__send_message(context, chat_id, self.lang_messages["confirmation_msg"], reply_markup=reply_markup)

    async def confirmation_button_click(self, update: Update, context: CustomContext):
        """
        This method handles the user's answer to the confirmation question.
        :param update: The update from Telegram.
        :param context: The context of the chat.
        """
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

    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        This method handles the inline query. This is run when you type: @botusername <query>
        :param update: The update from Telegram.
        :param context: The context of the chat.
        """
        query = update.inline_query.query
        if not query:
            return
        # get a generator of autocompleted words
        autocompleted = self.trie.autocomplete(query)
        if autocompleted is not None:
            ac = set(autocompleted)
            # create InlineQueryResultArticle for each autocompleted address
            results = sorted([
                InlineQueryResultArticle(
                    id=hashlib.md5(address.encode()).hexdigest(),
                    title=address,
                    input_message_content=InputTextMessageContent(address),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(self.lang_messages["select_msg"].format(address=address), callback_data=f",{address}")
                    ]])
                ) for address in ac
            ], key=lambda x: x.id)

            # respond with the results, limiting to the first 50
            await context.bot.answer_inline_query(update.inline_query.id, results[:50])

    @staticmethod
    def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        This method prints an error if the update causes one.
        :param update: The update from Telegram.
        :param context: The context of the chat.
        """
        print(f'Update {update} caused error {context.error}')

    async def set_frequency_command(self, update: Update, context: CustomContext) -> int:
        """
        This method starts the conversation to set the frequency.
        :param update: The update from Telegram.
        :param context: The context of the chat.
        :return: The next state to move to in the conversation.
        """
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
        """
        This method handles the user's choice of frequency.
        :param update: The update from Telegram.
        :param context: The context of the chat.
        :return: The next state to move to in the conversation.
        """
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
        """
        This method configures and starts the bot.
        """
        """ Setup and initialization code here... """
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

        # on inline queries - show corresponding inline results
        self.app.add_handler(InlineQueryHandler(self.inline_query))

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
    """
    Class to parse text, specifically separating text and images.
    """

    @staticmethod
    async def separate_text_and_image(text):
        """
        This method parses the passed text and separates out any 'img' elements and their src URLs.
        :param text: Text to parse.
        :return: Tuple containing a list of image urls and an object of parsed text.
        """
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
        """
        This method tries to get the answer text from the 'answeroptions' dictionary using the provided answer_key.
        :param question_data: Question data containing the 'answeroptions' field.
        :param answer_key: The key to lookup the 'answeroptions' field.
        :return: Answer corresponding to the answer_key or None if not found.
        """
        # Check if 'answeroptions' is an empty dictionary
        if not question_data.get('answeroptions'):
            return answer_key

        for option_key, option_data in question_data['answeroptions'].items():
            if option_key == answer_key:
                return option_data['answer']
        return None  # Return None if the answer_key is not found
