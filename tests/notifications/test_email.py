"""Почтовый канал (шаг F4, ADR-0018)."""

import pytest
from django.core import mail

from modules.notifications import api
from modules.notifications.domain import Channel, preferred

pytestmark = pytest.mark.django_db

IVANOV = 11


def test_a_bound_email_receives_the_dispatch():
    api.bind_channel(IVANOV, "email", "ivanov@example.com")
    api.enqueue_message(IVANOV, "Выставлен счёт за июль 2026: 21500 ₽.")

    sent, failed = api.dispatch_pending()

    assert (sent, failed) == (1, 0)
    (letter,) = mail.outbox
    assert letter.to == ["ivanov@example.com"]
    assert "21500" in letter.body


def test_the_messenger_beats_the_mailbox():
    """Порядок платформ — правило домена: мессенджер доходит быстрее письма."""
    channels = [Channel(IVANOV, "email", "a@b"), Channel(IVANOV, "telegram", "555")]
    assert preferred(channels).platform == "telegram"
    assert preferred([]) is None


def test_enqueue_prefers_the_messenger_when_both_are_bound():
    api.bind_channel(IVANOV, "email", "ivanov@example.com")
    api.bind_channel(IVANOV, "telegram", "555")

    message_id = api.enqueue_message(IVANOV, "т")

    (message,) = [m for m in api.list_messages(IVANOV)
                  if m.message_id == message_id]
    assert message.platform == "telegram"


def test_the_owner_binds_an_email_from_the_admin(admin_client):
    resp = admin_client.post("/admin/notifications/channel/add/", {
        "account_id": str(IVANOV), "platform": "email",
        "address": "ivanov@example.com"})

    assert resp.status_code == 302
    assert api.resolve_account_by_channel("email", "ivanov@example.com") == IVANOV


def test_the_admin_refuses_a_foreign_address(admin_client):
    api.bind_channel(IVANOV, "email", "ivanov@example.com")

    admin_client.post("/admin/notifications/channel/add/", {
        "account_id": "12", "platform": "email",
        "address": "ivanov@example.com"})

    assert api.resolve_account_by_channel("email", "ivanov@example.com") == IVANOV
