import re

from django.core.files.base import ContentFile
from django.utils import timezone

from ..models import Tenant
from .intake import attach_receipt, NoUnpaidStatementError
from .linking import link_chat, InvalidLinkCodeError

MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
HELP = "Отправьте фото чека об оплате. Чтобы привязать аккаунт: /start <код>."
START_RE = re.compile(r"^/start(?:\s+(?P<code>\S+))?")


def _period_ru(d):
    return f"{MONTHS_RU[d.month]} {d.year}"


def _find_tenant(msg):
    return Tenant.objects.filter(
        messenger_platform=msg.platform, messenger_chat_id=str(msg.chat_id)
    ).first()


def process_message(adapter, msg) -> str:
    text = msg.text or ""
    m = START_RE.match(text)
    if m:
        code = m.group("code")
        if not code:
            return "Укажите код: /start <код>. Код выдаёт арендодатель."
        try:
            tenant = link_chat(msg.platform, msg.chat_id, code)
        except InvalidLinkCodeError:
            return "Неверный код. Обратитесь к арендодателю."
        return f"Аккаунт привязан: {tenant}. Пришлите фото чека для оплаты."

    tenant = _find_tenant(msg)
    if msg.file_id:
        if tenant is None:
            return "Сначала привяжите аккаунт командой /start <код>."
        data = adapter.download_file(msg.file_id)
        name = msg.file_name or f"{msg.platform}_{timezone.now():%Y%m%d%H%M%S}.jpg"
        try:
            payment = attach_receipt(tenant, ContentFile(data, name=name), source=msg.platform)
        except NoUnpaidStatementError:
            return "Нет неоплаченных начислений."
        return (f"Чек получен, начисление за {_period_ru(payment.statement.period)} "
                f"отправлено на проверку.")

    if tenant is None:
        return "Здравствуйте! Привяжите аккаунт командой /start <код> (код выдаёт арендодатель)."
    return HELP


def handle_update(adapter, raw_update) -> None:
    msg = adapter.parse_update(raw_update)
    if msg is None:
        return
    reply = process_message(adapter, msg)
    if reply:
        adapter.send_message(msg.chat_id, reply)
