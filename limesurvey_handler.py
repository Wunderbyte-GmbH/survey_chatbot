import binascii

import requests as req
from collections import OrderedDict
import json
import base64
from datetime import datetime
from config import Config


class LimeSurveyHandler:

    def __init__(self, config: Config):
        self.config = config
        self.query = Query(config)

    def list_surveys(self):
        return self.query.execute_method("list_surveys", sUsername=self.query.LOGIN)

    def list_surveys_by_id(self, sid: int):
        for survey in self.list_surveys():
            if survey["sid"] == sid:
                return survey

    def list_groups(self, sid: int):
        return self.query.execute_method("list_groups", iSurveyID=sid)

    def list_questions(self, sid: int, gid: int):
        return self.query.execute_method("list_questions", iSurveyID=sid, iGroupID=gid)

    def list_survey_questions(self, sid: int):
        return self.query.execute_method("list_questions", iSurveyID=sid)

    def get_question_properties(self, qid: int):
        return self.query.execute_method("get_question_properties", iQuestionID=qid,
                                         aQuestionSettings=["answeroptions"])

    @staticmethod
    def _prepare_response_data(sid: int, additional_data: dict, seed="324567889"):
        now = datetime.now()
        formatted_date = now.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "iSurveyID": sid,
            "submitdate": formatted_date,
            "lastpage": 1,
            "startlanguage": "en",
            "seed": seed,
            **additional_data
        }

    def save_response(self, sid: int, seed: str, rdata: dict):
        response_data = self._prepare_response_data(sid, rdata, seed)
        return self.query.execute_method("add_response", iSurveyID=sid, aResponseData=response_data)

    def export_responses(self, sid: int):
        result = self.query.execute_method("export_responses", iSurveyID=sid, sDocumentType="csv", sLanguageCode="en",
                                           sCompletionStatus="full")

        # Decode the base64 encoded string
        if (isinstance(result, dict) and 'status' in result and
                result['status'] == 'No Data, survey table does not exist.'):
            print("No data available")
        else:
            base64_string = result
            try:
                decoded_string = base64.b64decode(base64_string)
                print(decoded_string)
                return decoded_string
            except binascii.Error:
                print("Invalid base64 string")

    def print_questions_in_all_surveys(self):
        # Iterate over all groups in each survey
        for survey in self.list_surveys():
            sid = survey["sid"]
            self.print_survey_questions(sid)

    def print_survey_questions(self, sid=None):
        if sid is None:
            for survey in self.list_surveys():
                self.print_survey_questions(survey["sid"])
        else:
            for group in self.list_groups(sid):
                gid = group["gid"]
                for question in self.list_questions(sid, gid):
                    qid = question["qid"]
                    print(f'{sid}-{gid}-{qid}')
                    print(question)
                    options = self.get_question_properties(qid)
                    print(options)


class Query:
    def __init__(self, config: Config):
        self.config = config
        self.HEADERS = config.HEADERS
        self.API_URL = config.API_URL
        self.LOGIN = config.LOGIN
        self.PASSWORD = config.PASSWORD
        self.sess_key = None

    @staticmethod
    def create_request_payload(method: str, params: dict):
        return OrderedDict([
            ("method", method),
            ("params", params),
            ("id", 1)
        ])

    def query(self, method: str, params: dict):
        data = json.dumps(self.create_request_payload(method, params))
        try:
            response = req.post(self.API_URL, headers=self.HEADERS, data=data)
            return response.json()
        except Exception as e:
            print(f"Error querying {method}: {e}")
            return []

    def execute_method(self, method: str, **kwargs):
        if self.sess_key is None:
            self._get_session_key()
        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            *[(k, v) for k, v in kwargs.items()]
        ])
        return self.query(method, params)["result"]

    def _get_session_key(self):
        if self.sess_key is None:
            params = OrderedDict([
                ("username", self.LOGIN),
                ("password", self.PASSWORD)
            ])
            response = self.query("get_session_key", params)
            if 'status' in response:
                raise RuntimeError(response['status'])
            self.sess_key = response["result"]
