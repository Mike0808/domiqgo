from django.core.management.base import BaseCommand, CommandError
from billing.messengers.telegram import TelegramAdapter

class Command(BaseCommand):
    help = "Register the Telegram webhook URL (production delivery)."

    def add_arguments(self, parser):
        parser.add_argument("url", help="Public HTTPS URL, e.g. "
                                        "https://domiq-ufa.ru/bot/telegram/webhook/")

    def handle(self, *args, **options):
        try:
            TelegramAdapter().set_webhook(options["url"])
        except Exception as exc:  # noqa: BLE001 - surface any API error to the operator
            raise CommandError(f"setWebhook failed: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Webhook set: {options['url']}"))
