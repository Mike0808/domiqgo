from datetime import date
from django.contrib.auth.models import User
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.messengers.base import IncomingMessage
from billing.services.bot import process_message, handle_update
from billing.services.linking import generate_link_code
from billing.tests.fakes import FakeAdapter

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_isolation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _tenant(chat_id=None):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    t = Tenant.objects.create(user=u, apartment=a, full_name="Иванов")
    if chat_id is not None:
        t.messenger_platform = "telegram"; t.messenger_chat_id = str(chat_id); t.save()
    return t, a


def _msg(**kw):
    kw.setdefault("platform", "telegram")
    kw.setdefault("chat_id", "555")
    return IncomingMessage(**kw)


def test_start_with_valid_code_links_chat():
    t, _ = _tenant()
    code = generate_link_code(t)
    reply = process_message(FakeAdapter(), _msg(text=f"/start {code}"))
    t.refresh_from_db()
    assert t.messenger_chat_id == "555"
    assert "привязан" in reply.lower()


def test_start_without_code_asks_for_it():
    reply = process_message(FakeAdapter(), _msg(text="/start"))
    assert "код" in reply.lower()


def test_start_with_bad_code_reports_error():
    reply = process_message(FakeAdapter(), _msg(text="/start nope"))
    assert "неверный код" in reply.lower()


def test_photo_from_linked_tenant_attaches_receipt(media_isolation):
    t, a = _tenant(chat_id=555)
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    adapter = FakeAdapter(file_bytes=b"receipt-bytes")
    reply = process_message(adapter, _msg(file_id="photo123"))
    assert "на проверку" in reply.lower()
    payment = Payment.objects.get()
    assert payment.statement.status == MonthlyStatement.PENDING
    assert payment.file.read() == b"receipt-bytes"
    assert payment.source == "telegram"


def test_photo_from_unlinked_chat_is_refused():
    reply = process_message(FakeAdapter(), _msg(file_id="photo123"))
    assert "привяжите" in reply.lower()
    assert Payment.objects.count() == 0


def test_photo_with_no_unpaid_statement_is_reported():
    t, a = _tenant(chat_id=555)
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="paid")
    reply = process_message(FakeAdapter(), _msg(file_id="photo123"))
    assert "нет неоплаченных" in reply.lower()


def test_plain_text_from_linked_tenant_gets_help():
    _tenant(chat_id=555)
    reply = process_message(FakeAdapter(), _msg(text="привет"))
    assert "чек" in reply.lower()


def test_handle_update_parses_then_sends():
    _tenant(chat_id=555)
    adapter = FakeAdapter(parsed=_msg(text="привет"))
    handle_update(adapter, {"any": "json"})
    assert len(adapter.sent) == 1
    assert adapter.sent[0][0] == "555"


def test_handle_update_ignores_irrelevant_update():
    adapter = FakeAdapter(parsed=None)
    handle_update(adapter, {"channel_post": {}})
    assert adapter.sent == []
