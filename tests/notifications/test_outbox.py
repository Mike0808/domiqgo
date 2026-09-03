"""Очередь и прогон отправки (шаг F2)."""

import pytest

from modules.notifications import api
from modules.notifications.infrastructure.models import DispatchRun

pytestmark = pytest.mark.django_db

IVANOV = 11


class _Transport:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send_message(self, chat_id, text):
        if self.fail:
            raise ConnectionError("сеть упала")
        self.sent.append((chat_id, text))


def test_enqueue_fixes_the_channel_and_dispatch_delivers(monkeypatch):
    api.bind_channel(IVANOV, "telegram", "555")
    message_id = api.enqueue_message(IVANOV, "Счёт выставлен")
    assert api.get_delivery_state(message_id) == "queued"

    transport = _Transport()
    monkeypatch.setattr(
        "modules.notifications.infrastructure.transports.transport_for",
        lambda platform: transport)
    sent, failed = api.dispatch_pending()

    assert (sent, failed) == (1, 0)
    assert transport.sent == [("555", "Счёт выставлен")]
    assert api.get_delivery_state(message_id) == "sent"
    assert DispatchRun.objects.count() == 1     # прогон оставил след


def test_a_recipient_without_channels_gets_nothing_queued():
    assert api.enqueue_message(IVANOV, "текст") is None
    assert api.list_messages(IVANOV) == []


def test_a_failed_delivery_stays_queued_and_exhausts_honestly(monkeypatch):
    api.bind_channel(IVANOV, "telegram", "555")
    message_id = api.enqueue_message(IVANOV, "т")
    monkeypatch.setattr(
        "modules.notifications.infrastructure.transports.transport_for",
        lambda platform: _Transport(fail=True))

    for _ in range(4):
        api.dispatch_pending()
        assert api.get_delivery_state(message_id) == "queued"
    sent, failed = api.dispatch_pending()

    assert (sent, failed) == (0, 1)
    assert api.get_delivery_state(message_id) == "failed"
    (message,) = api.list_messages(IVANOV)
    assert "ConnectionError" in message.last_error


def test_a_sent_message_is_not_picked_up_again(monkeypatch):
    api.bind_channel(IVANOV, "telegram", "555")
    api.enqueue_message(IVANOV, "т")
    transport = _Transport()
    monkeypatch.setattr(
        "modules.notifications.infrastructure.transports.transport_for",
        lambda platform: transport)
    api.dispatch_pending()
    api.dispatch_pending()   # второй прогон — инвариант 4

    assert len(transport.sent) == 1


def test_the_owner_resends_the_failed_and_cancels_the_queued(monkeypatch):
    api.bind_channel(IVANOV, "telegram", "555")
    failed_id = api.enqueue_message(IVANOV, "первое")
    monkeypatch.setattr(
        "modules.notifications.infrastructure.transports.transport_for",
        lambda platform: _Transport(fail=True))
    for _ in range(5):
        api.dispatch_pending()
    assert api.get_delivery_state(failed_id) == "failed"

    api.resend_message(failed_id)
    assert api.get_delivery_state(failed_id) == "queued"

    api.cancel_pending(failed_id)
    assert api.get_delivery_state(failed_id) == "cancelled"


def test_the_stale_queue_warning_is_loud(admin_client, monkeypatch):
    """Наблюдаемость: молчание прогона видно в админке."""
    from datetime import timedelta

    from django.utils import timezone

    from modules.notifications.infrastructure.models import OutgoingMessage

    api.bind_channel(IVANOV, "telegram", "555")
    message_id = api.enqueue_message(IVANOV, "т")
    OutgoingMessage.objects.filter(pk=message_id).update(
        queued_at=timezone.now() - timedelta(hours=2))

    page = admin_client.get("/admin/notifications/outgoingmessage/")

    assert "прогон" in page.content.decode()
