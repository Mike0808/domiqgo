from .base import MessengerAdapter

class MaxAdapter(MessengerAdapter):
    """Adapter for the MAX messenger (VK). Deferred to Plan 2B.

    MAX exposes a REST Bot API at platform-api.max.ru (webhook + long-polling),
    but publishing a bot requires a verified Russian legal entity (since Aug 2025),
    so this adapter is intentionally left unimplemented. It exists to prove the
    MessengerAdapter seam supports a second platform with no changes to bot.py.
    """
    platform = "max"

    def parse_update(self, raw_update):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def download_file(self, file_id):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def send_message(self, chat_id, text):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def set_webhook(self, url):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")
