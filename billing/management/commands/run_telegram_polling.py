import time
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from billing.messengers.telegram import TelegramAdapter, API
from billing.services.bot import handle_update

def poll_once(adapter, offset):
    """Fetch one batch of updates, dispatch each, return the next offset."""
    r = requests.get(f"{API}/bot{adapter.token}/getUpdates",
                     params={"offset": offset, "timeout": 25}, timeout=30)
    r.raise_for_status()
    updates = r.json().get("result", [])
    for update in updates:
        handle_update(adapter, update)
        offset = update["update_id"] + 1
    return offset

class Command(BaseCommand):
    help = "Poll Telegram for updates (development delivery)."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stderr.write("TELEGRAM_BOT_TOKEN is not set.")
            return
        adapter = TelegramAdapter()
        offset = 0
        self.stdout.write("Polling Telegram (Ctrl+C to stop)...")
        while True:
            try:
                offset = poll_once(adapter, offset)
            except requests.RequestException as exc:
                msg = str(exc)
                if adapter.token:
                    msg = msg.replace(adapter.token, "***")
                self.stderr.write("poll error: " + msg)
                time.sleep(3)
