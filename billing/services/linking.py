"""Привязка чата мессенджера — оркестрация двух модулей (ADR-0017).

Разделённая команда собрана целиком (шаг F1): Identity гасит код и говорит,
чья это запись; Notifications привязывает адрес. Оркеструет интерфейсный
слой бота — тот, кто разобрал входящее сообщение.
"""

from modules.identity import api as identity
from modules.notifications import api as notifications

from ..models import Tenant

InvalidLinkCodeError = identity.InvalidLinkCodeError
AddressAlreadyBound = notifications.AddressAlreadyBound


def generate_link_code(tenant):
    return identity.issue_link_code(tenant.user_id)


def link_chat(platform, chat_id, code):
    account_id = identity.redeem_link_code(code)
    notifications.bind_channel(account_id, platform, str(chat_id))
    return Tenant.objects.get(user_id=account_id)
