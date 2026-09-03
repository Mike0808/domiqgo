"""Прогон отправки по расписанию (cron/systemd-таймер) — шаг F2.

Наблюдаемость: каждый прогон оставляет строку в журнале; молчание журнала
видно в админке («сообщения старше часа в очереди»).
"""

from django.core.management.base import BaseCommand

from modules.notifications import api


class Command(BaseCommand):
    help = "Доставить накопившиеся уведомления"

    def handle(self, *args, **options):
        sent, failed = api.dispatch_pending()
        self.stdout.write(f"sent={sent} failed={failed}")
