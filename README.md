# Survey Chatbot

**Survey Chatbot** designed to interact with users via the Telegram messaging platform and integrate with LimeSurvey for survey functionality. 
It retrieves questions from LimeSurvey using a specified survey ID, delivers these questions individually to users of the designated Telegram bot, and subsequently records responses back to LimeSurvey. Notably, users are restricted from submitting multiple responses to the survey. Furthermore, it is important that all questions defined in the survey are of the List (radio) type.

Refer to the instructions provided below for configuring and deploying the chatbot.
## Prerequisites

- Install Python Version Management [pyenv](https://github.com/pyenv/pyenv)
- Ensure that LimeSurvey is installed, and a survey has been created
- Create a telegram bot [@BotFather](https://telegram.me/BotFather) and ensure to store this token for future use
- Add the required commands to your telegram bot
In [@BotFather](https://telegram.me/BotFather) type /setcommands, select the bot that you created in previous step, and enter the following text:
```
start - start survey
setfrequency- set frequency
help - show help
cancel - cancel survey
```
- Install Apache and configure Reverse Proxy Configuration for survey_chatbot in your enabled site
```
     # Reverse Proxy Configuration for survey_chatbot
     ProxyPass /surveybot http://127.0.0.1:8000
     ProxyPassReverse /surveybot http://127.0.0.1:8000
```
```
service apache2 restart
```

Note that the words "start", "setfrequency", "help" and "cancel" should not be changed, but the messages in front of them can be changed.

## Setting Up

### Clone the project
```
git clone git@github.com:Wunderbyte-GmbH/survey_chatbot.git
```
### Install python
Install desired Python version(3.9 or higher) using pyenv, and set it as default python for survey_chatbot:
```
pyenv install -v 3.12.0
cd /path/to/survey_chatbot
pyenv local 3.12.0
```

- Install Required Python packages:
  - python-telegram-bot
  - python-telegram-bot[job-queue]
  - python-telegram-bot[webhooks]
  - Flask
  - asgiref
  - beautifulsoup4
  - uvicorn
  - requests

- Install the required Python packages:
```
cd /path/to/survey_chatbot
pip install --upgrade pip
pip install python-telegram-bot python-telegram-bot[job-queue] python-telegram-bot[webhooks] Flask asgiref beautifulsoup4 uvicorn requests
```

## Running the Survey Chatbot
### Manual execution
1- Set environment variables

Before running the Survey Chatbot, make sure to set the required environment variables:
```
export TOKEN="your_telegram_bot_token"  # token generated by @BotFather
export BOT_USERNAME="@Your_Bot_Username"
export URL="https://your_domain/surveybot"
export PORT="8000" # Ensure that the firewall configuration allows incoming connections on port 8000
export HOST="127.0.0.1"
export HEADERS="{"content-type": "application/json"}"
export API_URL="https://your_domain/index.php/admin/remotecontrol"
export LOGIN='your_limesurvey_admin_username'  # Using single quote is recommended
export PASSWORD="your_limesurvey_admin_password"
export SURVEY_ID="your_survey_id"
export LANG="de"   # Can be "en" or "de"
```
You can also add the export commands in .bashrc, then you don't need to re-run them 

2- Run the Survey Chatbot using Python interpreter managed by pyenv

Take the python path:
```
cd /path/to/survey_chatbot
which python
```
Use the python located in path from the previous commands output to run the project:
```
/path/to/pyenv/managed/python main.py
```
### Service based execution
To make the execution of the Survey Chatbot more convenient, you can define a system service for it. 

To redirect Telegram requests to the Survey Chatbot Flask application, follow these steps:

1- Edit the service file:
```
nano /etc/systemd/system/survey_chatbot.service
```

2- Add the following configuration:
```
[Unit]
Description=Survey Chatbot Service
After=network.target

[Service]
ExecStart=/path/to/pyenv/managed/python /path/to/survey_chatbot/main.py
WorkingDirectory=<path to survey_chatbot>
Restart=always
RestartSec=5
EnvironmentFile=/path/to/variables

[Install]
WantedBy=default.target
```
3- Create a variables file:
```
cat /path/to/variables
TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
BOT_USERNAME="@Your_Bot_Username"
URL="https://your_domain/surveybot"
PORT="8000"
HOST="127.0.0.1"
HEADERS="{\"content-type\": \"application/json\"}"
API_URL="https://your_limesurvey_url/index.php/admin/remotecontrol"
LOGIN="your_limesurvey_username"
PASSWORD='your_limesurvey_password'
SURVEY_ID="your_survey_id"
LANG="de"
```

4- Reload systemd daemon:
```
sudo systemctl enable survey_chatbot
systemctl daemon-reload
```

## Adjustment of the text of messages
You can edit the text of messages that are sent to users using messages_en.py or messages_de.py.
Pay attention that the variable names and variable placeholders in the middle of the text untouched.

## Notes
The bash commands outlined in this README are tailored for Ubuntu. If you're using a different operating system, please adjust the commands accordingly. 
