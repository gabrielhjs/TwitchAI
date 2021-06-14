import requests
import inspect

from loguru import logger
from typing import Text, Callable, Awaitable, Any

from irc import bot
from irc.client import ServerConnection, Event
from rasa.core.channels import InputChannel, UserMessage, OutputChannel
from sanic import Blueprint, response as sanic_response
from sanic.request import Request
from sanic.response import HTTPResponse


class TwitchConnection(bot.SingleServerIRCBot):
    def __init__(
        self,
        username: str,
        client_id: str,
        token: str,
        channel: str
    ):
        self.client_id = client_id
        self.token = token
        self.channel = '#' + channel

        super().__init__(
            [("irc.chat.twitch.tv", 6667, f"oauth:{token}",)],
            username,
            username,
        )

        self._connect()

    def on_welcome(self, connection: ServerConnection, _: Event):
        logger.info('Joining ' + self.channel)

        # You must request specific capabilities before you can use them
        connection.cap('REQ', ':twitch.tv/membership')
        connection.cap('REQ', ':twitch.tv/tags')
        connection.cap('REQ', ':twitch.tv/commands')
        connection.join(self.channel)

    def on_pubmsg(self, connection: ServerConnection, event: Event):
        sender_id = next(item for item in event.tags if item["key"] == "display-name").get("value")
        text = event.arguments[0]

        try:
            response = requests.post(
                "http://localhost:5005/webhooks/twitch/webhook",
                json={
                    "sender": sender_id,
                    "text": text
                }
            ).json()
        except requests.exceptions.ConnectionError as error:
            logger.error(error)

        else:
            logger.info(f"Sending to: {response.get('recipient_id')} | {response.get('text')}")
            connection.privmsg(self.channel, f"{response.get('recipient_id')}, {response.get('text')}")


class TwitchInputChannel(InputChannel):

    def blueprint(self, on_new_message: Callable[[UserMessage], Awaitable[Any]]) -> Blueprint:
        custom_webhook = Blueprint(
            "custom_webhook_{}".format(type(self).__name__),
            inspect.getmodule(self).__name__,
        )

        @custom_webhook.route("/", methods=["GET"])
        async def health(_: Request) -> HTTPResponse:
            return sanic_response.json({"status": "ok"})

        @custom_webhook.route("/webhook", methods=["POST"])
        async def receive(request: Request) -> HTTPResponse:
            sender_id = request.json.get("sender")  # method to get sender_id
            text = request.json.get("text")  # method to fetch text
            input_channel = self.name()  # method to fetch input channel
            metadata = self.get_metadata(request)  # method to get metadata

            collector = TwitchOutputChannel()

            # include exception handling

            await on_new_message(
                UserMessage(
                    text,
                    collector,
                    sender_id,
                    input_channel=input_channel,
                    metadata=metadata,
                )
            )

            return sanic_response.json(collector.message)

        return custom_webhook

    @classmethod
    def name(cls) -> Text:
        return "twitch"


class TwitchOutputChannel(OutputChannel):
    message: dict

    async def send_text_message(self, recipient_id: Text, text: Text, **kwargs: Any) -> None:
        self.message = {
            "recipient_id": recipient_id,
            "text": text
        }


if __name__ == "__main__":
    TwitchConnection(
        "chatbot_ai",
        "ongxbokkg6qr8i1qfnz5kgo7ks7mc0",
        "yac2mcdoofdvjw7jqoz7uzlolqoksf",
        "gabrielhjs"
    ).start()
