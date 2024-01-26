from limesurvey_handler import LimeSurveyHandler


class SurveyData:
    def __init__(self, sid: int):
        self.__sid = sid
        self.__limesurvey_handler = LimeSurveyHandler()
        self.__survey_questions = self.__build_questions(self.__sid)

    def sid(self):
        return self.__sid

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

    def __create_question_item(self, sid, gid, question) -> dict:
        qid = question["qid"]
        code = self.__construct_code(sid, gid, qid)
        options = self.__limesurvey_handler.get_question_properties(qid)
        answer_options = options.get('answeroptions', {})
        question_dict = {
            'id': qid,
            'code': code,
            'question': question['question'],
            'answeroptions': {key: {'answer': answer_options[key].get('answer')} for key in answer_options}
        }
        return question_dict

    @staticmethod
    def __construct_code(sid, gid, qid) -> str:
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
