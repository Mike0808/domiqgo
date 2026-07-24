from billing.messengers.base import MessengerAdapter


class FakeAdapter(MessengerAdapter):
    platform = "telegram"

    def __init__(self, parsed=None, file_bytes=b"img"):
        self._parsed = parsed
        self._file_bytes = file_bytes
        self.sent = []          # list of (chat_id, text)

    def parse_update(self, raw_update):
        # In handle_update tests, `parsed` is what parse_update yields.
        return self._parsed

    def download_file(self, file_id):
        return self._file_bytes

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    def set_webhook(self, url):
        pass
