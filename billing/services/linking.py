"""Привязка чата мессенджера к жильцу.

Код привязки уехал в `modules/identity/` шагом C4c: он доказывает личность,
а не адрес доставки. Здесь осталась вторая половина — запись платформы и
чата, — и она ждёт модуля Notifications (`BindChannel`, ADR-0017). Порядок
уже целевой: сначала Identity говорит, чья это запись, потом привязывается
канал.
"""

from modules.identity import api as identity

from ..models import Tenant

InvalidLinkCodeError = identity.InvalidLinkCodeError


def generate_link_code(tenant):
    return identity.issue_link_code(tenant.user_id)


def link_chat(platform, chat_id, code):
    account_id = identity.redeem_link_code(code)
    tenant = Tenant.objects.get(user_id=account_id)
    tenant.messenger_platform = platform
    tenant.messenger_chat_id = str(chat_id)
    tenant.save(update_fields=["messenger_platform", "messenger_chat_id"])
    return tenant
