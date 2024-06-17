import re
from limesurvey_handler import LimeSurveyHandler
from urllib.parse import urlparse


class SurveyData:

    def __init__(self, sid: int, limesurvey_handler: LimeSurveyHandler):
        """
        Initializes the SurveyData object.

        :param sid: The id of the survey
        :param limesurvey_handler: An instance of the LimeSurveyHandler
        """
        self.__survey_id = sid
        self.__limesurvey_handler = limesurvey_handler
        self.__html_cleaner = HTMLCleaner(self.__limesurvey_handler.config.API_URL)
        self.__survey_questions = self.__build_questions(self.__survey_id)

    def sid(self):
        """
        Returns the survey id

        :return: The id of the survey
        """
        return self.__survey_id

    def question_list(self):
        """
        Returns the list of survey questions

        :return: List of survey questions
        """
        return self.__survey_questions

    def __build_questions(self, sid: int) -> list:
        """
        Builds a list of questions from the survey id

        :param sid: The id of the survey
        :return: The list of questions
        """
        result = []

        for group in self.__limesurvey_handler.list_groups(sid):
            gid = group["gid"]
            question_list = self.__limesurvey_handler.list_questions(sid, gid)
            for question in sorted(question_list, key=lambda question: question['question_order']):
                question_dict = self.__create_question_item(sid, gid, question)
                """ Append the question dictionary to the result list"""
                result.append(question_dict)

        return result

    def __create_question_item(self, sid: int, gid: int, question: list) -> dict:
        """
        Creates a dictionary of question items

        :param sid: The id of the survey
        :param gid: The id of a group in the survey
        :param question: A list containing question information
        :return: A dictionary containing question data
        """
        qid = question["qid"]
        code = self.__construct_question_code(sid, gid, qid)
        options = self.__limesurvey_handler.get_question_properties(qid)
        answer_options = options.get('answeroptions', {})
        question['question'] = self.__html_cleaner.refine_html_text(question['question'])
        if isinstance(answer_options, dict):
            answeroptions = {key: {'answer': value.get('answer')} for key, value in answer_options.items()}
        else:
            answeroptions = {}
        question_dict = {
            'id': qid,
            'code': code,
            'question': question['question'],
            'answeroptions': answeroptions
        }
        return question_dict

    @staticmethod
    def __construct_question_code(sid: int, gid: int, qid: int) -> str:
        """
        Constructs a question code from survey id, group id and question id

        :param sid: The id of the survey
        :param gid: The id of a group in the survey
        :param qid: The id of a question in the survey
        :return: A string representing the question code
        """
        return f'{sid}X{gid}X{qid}'

    def save_survey_response(self, sid: int, chat_id: int, response_data: dict) -> int:
        """
        Saves the response of a survey

        :param sid: The id of the survey
        :param chat_id: The id of the chat
        :param response_data: The response data of the survey
        :return: A result int value
        """
        filtered_response_data = self.__filter_response_data(sid, response_data)
        seed = self.get_last_nine_digits(chat_id)
        result = self.__limesurvey_handler.save_response(sid, seed, filtered_response_data)
        print(result)
        return result

    @staticmethod
    def __filter_response_data(sid: int, response_data: dict) -> dict:
        """
        Filters the 'response_data' dictionary to only contain key,value pairs where keys starts with 'sid'.

        :param sid: ID to be compared with keys in dictionary.
        :param response_data: the dictionary from which data is to be filtered out.
        :return: A dictionary containing filtered data.
        """
        """ Filter response_data to only contain question ID and answer ID"""
        first_item_value = next(iter(response_data.values()))
        return {key: value for key, value in first_item_value.items() if key.startswith(str(sid))}

    @staticmethod
    def get_last_nine_digits(chat_id: int):
        """
        Extracts the last nine digits from 'chat_id'

        :param chat_id: input number
        :return: last nine digits of 'chat_id' as string.
        """
        str_chat_id = str(chat_id)
        first_nine_chars = str_chat_id[-9:]
        return first_nine_chars

    def print_survey_dict(self):
        """
        Prints the '__survey_questions' which is an instance attribute.

        :return: None.
        """
        print(self.__survey_questions)


class HTMLCleaner:
    def __init__(self, url: str):
        """
        Initializes 'HTMLCleaner' object and also extracts base url from 'url' and assign it to '__base_url'

        :param url: input url from which base url is to be extracted.
        """
        self.__base_url = self.extract_base_url(url)

    def refine_html_text(self, text: str):
        """
        Performs a series of cleaning operations on 'text'

        :param text : The string which is to be cleaned.
        :return: 'text' after a series of cleaning operations performed on it.
        """
        new_text = HTMLCleaner.replace_br_src(text)
        new_text = self.replace_img_src(new_text)
        new_html = self.replace_paragraph_tags(new_text)
        return new_html

    def replace_img_src(self, html_string: str):
        """
        Replaces the image source link in 'html_string' with a new link.

        :param html_string: The string in which the replacement needs to be done.
        :return: 'html_string' after replacing the image source link.
        """
        img_src_pattern = r'src="(/upload/surveys/\d+/images/[^"]+)"'
        img_src_replacement = f'src="{self.__base_url}\\1"'
        new_html = re.sub(img_src_pattern, img_src_replacement, html_string)
        return new_html

    @staticmethod
    def replace_br_src(html_string: str):
        """
        Replaces "<br />" in 'html_string' with "\n"

        :param html_string: The string in which the replacement needs to be done.
        :return: 'html_string' after "<br />" is replaced with "\n".
        """
        new_html = html_string.replace("<br />", "\n")
        return new_html

    @staticmethod
    def replace_paragraph_tags(html_string: str):
        """
        Replaces "<p>" and "</p>" in 'html_string' with "\n" and "", respectively.

        :param html_string : The string in which the replacement needs to be done.
        :return: 'html_string' after "<p>" and "</p>" are replaced with "\n" and "".
        """
        return html_string.replace("<p>", "\n").replace("</p>", "")

    @staticmethod
    def extract_base_url(url: str):
        """
        Extracts base url from a given 'url'.

        :param url: The url from which base url is to be extracted.
        :return: The base url.
        """
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        return base_url
