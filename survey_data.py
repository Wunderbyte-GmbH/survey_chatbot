import re
from limesurvey_handler import LimeSurveyHandler
from urllib.parse import urlparse


class SurveyData:

    def __init__(self, sid: int, limesurvey_handler: LimeSurveyHandler):
        self.__survey_id = sid
        self.__limesurvey_handler = limesurvey_handler
        self.__base_url = self.extract_base_url(limesurvey_handler.config.API_URL)
        self.__survey_questions = self.__build_questions(self.__survey_id)

    def sid(self):
        return self.__survey_id

    def question_list(self):
        return self.__survey_questions

    def __build_questions(self, sid: int) -> list:
        result = []

        for group in self.__limesurvey_handler.list_groups(sid):
            gid = group["gid"]

            for question in self.__limesurvey_handler.list_questions(sid, gid):
                question_dict = self.__create_question_item(sid, gid, question)
                """ Append the question dictionary to the result list"""
                result.append(question_dict)

        return result

    def __create_question_item(self, sid: int, gid: int, question: list) -> dict:
        qid = question["qid"]
        code = self.__construct_question_code(sid, gid, qid)
        options = self.__limesurvey_handler.get_question_properties(qid)
        answer_options = options.get('answeroptions', {})
        question['question'] = self.refine_html_text(question['question'])
        question_dict = {
            'id': qid,
            'code': code,
            'question': question['question'],
            'answeroptions': {key: {'answer': answer_options[key].get('answer')} for key in answer_options}
        }
        return question_dict

    @staticmethod
    def __construct_question_code(sid: int, gid: int, qid: int) -> str:
        return f'{sid}X{gid}X{qid}'

    def save_survey_response(self, sid: int, response_data: dict) -> int:
        filtered_response_data = self.__filter_response_data(sid, response_data)

        result = self.__limesurvey_handler.save_response(sid, filtered_response_data)
        print(result)
        return result

    @staticmethod
    def __filter_response_data(sid: int, response_data: dict) -> dict:
        """ Filter response_data to only contain question ID and answer ID"""
        first_item_value = next(iter(response_data.values()))
        return {key: value for key, value in first_item_value.items() if key.startswith(str(sid))}

    def print_survey_dict(self):
        """ Print method to display the survey_dict"""
        print(self.__survey_questions)

    @staticmethod
    def extract_base_url(url: str):
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        return base_url

    def refine_html_text(self, text: str):
        new_text = SurveyData.replace_br_src(text)
        new_html = self.replace_img_src(new_text)

        return new_html

    def replace_img_src(self, html_string: str):
        img_src_pattern = r'src="(/upload/surveys/\d+/images/[^"]+)"'
        img_src_replacement = f'src="{self.__base_url}\\1"'
        new_html = re.sub(img_src_pattern, img_src_replacement, html_string)
        return new_html

    @staticmethod
    def replace_br_src(html_string: str):
        new_html = html_string.replace("<br />", "\n")
        return new_html
