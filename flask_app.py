import uvicorn
from flask import Flask, request, Response, make_response
from http import HTTPStatus
from asgiref.wsgi import WsgiToAsgi
import os

from telegram import Update


class FlaskApp:
    def __init__(self, app):
        self.app = app
        self.flask_app = Flask(__name__)
        self.port = int(os.getenv("PORT"))
        if self.port is None:
            raise ValueError("PORT environment variable is not set.")

        @self.flask_app.post("/telegram")  # type: ignore[misc]
        async def telegram() -> Response:
            """Handle incoming Telegram updates by putting them into the `update_queue`"""
            await self.app.update_queue.put(Update.de_json(data=request.json, bot=self.app.bot))
            return Response(status=HTTPStatus.OK)

        @self.flask_app.get("/healthcheck")  # type: ignore[misc]
        async def health() -> Response:
            """For the health endpoint, reply with a simple plain text message."""
            response = make_response("The bot is still running fine :)", HTTPStatus.OK)
            response.mimetype = "text/plain"
            return response

    def run(self):
        return uvicorn.Server(
            config=uvicorn.Config(
                app=WsgiToAsgi(self.flask_app),
                port=self.port,
                use_colors=False,
                host="127.0.0.1",
            )
        )
