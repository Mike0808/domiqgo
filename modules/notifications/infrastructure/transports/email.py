"""Почтовый транспорт (шаг F4, ADR-0018).

Не `MessengerAdapter`: у почты нет входящих, вебхуков и файлов — прогону
отправки нужен только `send_message`, и порт очереди ровно таков.
"""

from django.conf import settings
from django.core.mail import send_mail


class EmailTransport:
    platform = "email"

    def send_message(self, chat_id: str, text: str) -> None:
        """`chat_id` здесь — почтовый адрес: подпись общая с мессенджерами."""
        send_mail(subject=settings.EMAIL_SUBJECT, message=text,
                  from_email=None,          # DEFAULT_FROM_EMAIL
                  recipient_list=[chat_id], fail_silently=False)
