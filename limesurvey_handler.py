import binascii

import requests as req
from collections import OrderedDict
import json
import base64
from datetime import datetime
import os


class LimeSurveyHandler:

    def __init__(self):
        self.query = Query()

    def list_surveys(self):
        return self.query.execute_method("list_surveys", sUsername=self.query.login)

    def list_surveys_by_id(self, sid):
        for survey in self.list_surveys():
            if survey["sid"] == sid:
                return survey

    def list_groups(self, sid):
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

    def save_response(self, sid: int, rdata: dict):
        response_data = self._prepare_response_data(sid, rdata)
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
    def __init__(self):
        # Read values from environment variables
        self.headers = json.loads(os.getenv("HEADERS"))
        self.api_url = os.getenv("API_URL")
        self.login = os.getenv("LOGIN")
        self.password = os.getenv("PASSWORD")
        self.sess_key = None
        if self.headers is None:
            raise ValueError("HEADERS environment variable is not set.")
        if self.api_url is None:
            raise ValueError("API_URL environment variable is not set.")
        if self.login is None:
            raise ValueError("LOGIN environment variable is not set.")
        if self.password is None:
            raise ValueError("PASSWORD environment variable is not set.")

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
            response = req.post(self.api_url, headers=self.headers, data=data)
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
                ("username", self.login),
                ("password", self.password)
            ])
            self.sess_key = self.query("get_session_key", params)["result"]
