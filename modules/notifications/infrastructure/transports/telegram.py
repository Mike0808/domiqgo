import requests
from django.conf import settings
from .base import MessengerAdapter, IncomingMessage

API = "https://api.telegram.org"

class TelegramAdapter(MessengerAdapter):
    platform = "telegram"

    def __init__(self, token=None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN

    def _method(self, name):
        return f"{API}/bot{self.token}/{name}"

    def parse_update(self, raw_update):
        message = raw_update.get("message") or raw_update.get("edited_message")
        if not message:
            return None
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "")
        file_id = ""
        file_name = ""
        if message.get("photo"):
            file_id = message["photo"][-1]["file_id"]      # largest size last
        elif message.get("document"):
            file_id = message["document"]["file_id"]
            file_name = message["document"].get("file_name", "")
        return IncomingMessage(platform=self.platform, chat_id=chat_id,
                               text=text, file_id=file_id, file_name=file_name)

    def download_file(self, file_id):
        r = requests.get(self._method("getFile"), params={"file_id": file_id}, timeout=30)
        r.raise_for_status()
        path = r.json()["result"]["file_path"]
        fr = requests.get(f"{API}/file/bot{self.token}/{path}", timeout=60)
        fr.raise_for_status()
        return fr.content

    def send_message(self, chat_id, text):
        r = requests.post(self._method("sendMessage"),
                          json={"chat_id": chat_id, "text": text}, timeout=30)
        r.raise_for_status()

    def set_webhook(self, url):
        r = requests.post(self._method("setWebhook"),
                          json={"url": url, "secret_token": settings.TELEGRAM_WEBHOOK_SECRET},
                          timeout=30)
        r.raise_for_status()
