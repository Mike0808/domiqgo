import secrets
from ..models import Tenant

class InvalidLinkCodeError(Exception):
    """The supplied link code was empty or matched no tenant."""

def generate_link_code(tenant):
    code = secrets.token_urlsafe(8)
    tenant.link_code = code
    tenant.save(update_fields=["link_code"])
    return code

def link_chat(platform, chat_id, code):
    code = (code or "").strip()
    if not code:
        raise InvalidLinkCodeError("Неверный код.")
    tenant = Tenant.objects.filter(link_code=code).first()
    if tenant is None:
        raise InvalidLinkCodeError("Неверный код.")
    tenant.messenger_platform = platform
    tenant.messenger_chat_id = str(chat_id)
    tenant.link_code = ""
    tenant.save(update_fields=["messenger_platform", "messenger_chat_id", "link_code"])
    return tenant
