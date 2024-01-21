import binascii

import requests as req
from collections import OrderedDict
import json
import base64
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

class LimeSurveyHandler:

    def __init__(self):
        # Read values from environment variables
        self.headers = json.loads(os.getenv("HEADERS"))
        self.api_url = os.getenv("API_URL")
        self.login = os.getenv("LOGIN")
        self.password = os.getenv("PASSWORD")
        self.sess_key = None

    def query(self, method, params):

        data = OrderedDict([
            ("method", method),
            ("params", params),
            ("id", 1)
        ])

        data = json.dumps(data)

        try:
            r = req.post(self.api_url, headers=self.headers, data=data)
            return r.json()
        except Exception as e:
            print(f"Error querying {method}: {e}")
            return []

    def get_session_key(self):
        method = "get_session_key"

        params = OrderedDict([
            ("username", self.login),
            ("password", self.password)
        ])
        if self.sess_key is None:
            self.sess_key = self.query(method, params)["result"]
        return self.sess_key

    def list_surveys(self):
        self.get_session_key()
        method = "list_surveys"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("sUsername", self.login)
        ])

        return self.query(method, params)["result"]


    def list_surveys_by_id(self, sid):
        s=self.list_surveys()
        for survey in self.list_surveys():
            if survey["sid"] == sid:
                return survey

    def list_groups(self, sid):
        self.get_session_key()
        method = "list_groups"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iSurveyID", sid)
        ])

        return self.query(method, params)["result"]


    def list_questions(self, sid, gid):
        self.get_session_key()
        method = "list_questions"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iSurveyID", sid),
            ("iGroupID", gid)
        ])

        return self.query(method, params)["result"]


    def list_survey_questions(self, sid):
        self.get_session_key()
        method = "list_questions"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iSurveyID", sid)
        ])

        return self.query(method, params)["result"]

    def get_question_properties(self, sid, gid, qid):
        self.get_session_key()
        method = "get_question_properties"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iQuestionID", qid),
            ("aQuestionSettings", ["answeroptions"])
        ])

        return self.query(method, params)["result"]

    def add_response(self, sid, rdata):
        self.get_session_key()
        # Get the current date and time
        now = datetime.now()
        # Format the date and time
        formatted_date = now.strftime("%Y-%m-%d %H:%M:%S")

        response_data = {
            "iSurveyID": sid,
            "submitdate": formatted_date,
            "lastpage": 1,
            "startlanguage": "en",
            "seed": "324567889", # Check this value later
        }
        response_data.update(rdata)

        method = "add_response"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iSurveyID", sid),
            ("aResponseData", response_data)
        ])

        return self.query(method, params)["result"]

    def export_responses(self, sid):
        self.get_session_key()
        method = "export_responses"

        params = OrderedDict([
            ("sSessionKey", self.sess_key),
            ("iSurveyID", sid),
            ("sDocumentType", "csv"),
            ("sLanguageCode", "en"),
            ("sCompletionStatus", "full")
        ])

        result = self.query(method, params)["result"]
        # Decode the base64 encoded string
        if isinstance(result, dict) and 'status' in result and result['status'] == 'No Data, survey table does not exist.':
            print("No data available")
        else:
            base64_string = result
            try:
                decoded_string = base64.b64decode(base64_string)
                print(decoded_string)
                return decoded_string
            except binascii.Error:
                print("Invalid base64 string")

    def save_response(self, sid, response_data):
        return self.add_response(sid, response_data)

    def print_survey_questions(self,sid):
        self.get_session_key()

        # Iterate over all groups in each survey
        survey=self.list_surveys_by_id(int(sid))
        for group in self.list_groups(sid):
            gid = group["gid"]
            # Iterate over all questions in each group
            for question in self.list_questions(sid, gid):
                qid = question["qid"]
                print(f'{sid}-{gid}-{qid}')
                print(question)
                options = self.get_question_properties(sid, gid, qid)
                print(options)

    def print_questions_in_all_surveys(self):
        self.get_session_key()
        # Iterate over all groups in each survey
        for survey in self.list_surveys():
            sid = survey["sid"]
            for group in self.list_groups(sid):
                gid = group["gid"]
                # Iterate over all questions in each group
                for question in self.list_questions(sid, gid):
                    qid = question["qid"]
                    print(f'{sid}-{gid}-{qid}')
                    print(question)
                    options = self.get_question_properties(sid, gid, qid)
                    print(options)
