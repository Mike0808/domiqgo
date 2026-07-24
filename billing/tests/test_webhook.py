import json
from datetime import date
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

WEBHOOK = "/bot/telegram/webhook/"

def _linked_tenant(chat_id=555):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    Tenant.objects.create(user=u, apartment=a, full_name="Иванов",
                          messenger_platform="telegram", messenger_chat_id=str(chat_id))
    return a

def test_webhook_rejects_missing_secret(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="{}", content_type="application/json")
    assert resp.status_code == 403

def test_webhook_rejects_wrong_secret(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="{}", content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="nope")
    assert resp.status_code == 403

def test_webhook_processes_text_update(settings, monkeypatch):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    _linked_tenant(555)
    # Don't hit the network on the outbound reply.
    import billing.messengers.telegram as tg
    sent = {}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {}
    monkeypatch.setattr(tg.requests, "post",
                        lambda url, json=None, timeout=None: sent.update(json or {}) or Resp())
    body = json.dumps({"message": {"chat": {"id": 555}, "text": "привет"}})
    resp = Client().post(WEBHOOK, data=body, content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
    assert resp.status_code == 200
    assert sent.get("chat_id") == "555"          # a reply was sent to this chat

def test_webhook_bad_json_returns_400(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="not-json", content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
    assert resp.status_code == 400

def test_webhook_swallows_handler_exception(settings, monkeypatch):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    import billing.webhooks as webhooks

    def _boom(adapter, raw):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhooks, "handle_update", _boom)
    body = json.dumps({"message": {"chat": {"id": 555}, "text": "hi"}})
    resp = Client().post(WEBHOOK, data=body, content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
    assert resp.status_code == 200

def test_unset_secret_rejects_all_requests(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = ""
    body = json.dumps({"message": {"chat": {"id": 555}, "text": "hi"}})
    resp_no_header = Client().post(WEBHOOK, data=body, content_type="application/json")
    assert resp_no_header.status_code == 403
    resp_empty_header = Client().post(WEBHOOK, data=body, content_type="application/json",
                                      HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="")
    assert resp_empty_header.status_code == 403
