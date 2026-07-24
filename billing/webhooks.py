import hmac
import json
import logging
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from .messengers.telegram import TelegramAdapter
from .services.bot import handle_update

logger = logging.getLogger(__name__)

@csrf_exempt
def telegram_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.TELEGRAM_WEBHOOK_SECRET or not hmac.compare_digest(
        secret, settings.TELEGRAM_WEBHOOK_SECRET
    ):
        return HttpResponseForbidden("bad secret")
    try:
        raw = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    try:
        handle_update(TelegramAdapter(), raw)
    except Exception:
        logger.exception("telegram update processing failed")
    return HttpResponse("ok")
