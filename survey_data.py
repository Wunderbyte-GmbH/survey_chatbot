from limesurvey_handler import LimeSurveyHandler

class SurveyData:
    def __init__(self, sid:int):
        self.sid=sid
        self.limesurvey_handler = LimeSurveyHandler()
        self.survey_dict = self.create_question_dictionary(self.sid)

    # Set method to update the survey_dict
    def set_survey_dict(self, new_survey_dict):
        self.survey_dict = new_survey_dict


    # Get method to retrieve the survey_id
    def get_survey_id(self):
        return self.sid

    # Print method to display the survey_id
    def print_survey_id(self):
        print(self.sid)


    # Get method to retrieve the survey_dict
    def get_survey_dict(self):
        return self.survey_dict

    # Print method to display the survey_dict
    def print_survey_dict(self):
        print(self.survey_dict)

    def create_question_dictionary(self, sid):
      self.limesurvey_handler.get_session_key()
      result = []

      # Get survey details
      survey = self.limesurvey_handler.list_surveys_by_id(sid)

      # Iterate over groups in the survey
      for group in self.limesurvey_handler.list_groups(sid):
          gid = group["gid"]

          # Iterate over questions in each group
          for question in self.limesurvey_handler.list_questions(sid, gid):
              qid = question["qid"]

              # Construct the code based on the specified format
              code = f'{sid}X{gid}X{qid}'

              # Get question properties including answer options
              options = self.limesurvey_handler.get_question_properties(sid, gid, qid)
              answer_options = options.get('answeroptions', {})

              # Create the dictionary for the current question
              question_dict = {
                  'id': qid,
                  'code': code,
                  'question': question['question'],
                  'answeroptions': {key: {'answer': answer_options[key].get('answer')} for key in answer_options}
              }

              # Append the question dictionary to the result list
              result.append(question_dict)

      return result

    def save_survey_response(self, sid, response_data):
        # Filter response_data to only contain question ID and answer ID
        filtered_response_data = {key: value for key, value in response_data.items() if key.startswith(str(sid))}
        result = self.limesurvey_handler.save_response(sid, filtered_response_data)
        return result

