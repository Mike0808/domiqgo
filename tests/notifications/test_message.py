"""Исходящее сообщение — правила без базы (инварианты 4–6)."""

import pytest

from modules.notifications.domain import (
    MAX_ATTEMPTS, AlreadySent, NotFailed, NotQueued, OutgoingMessage,
)


def _message(state="queued", attempts=0):
    return OutgoingMessage(message_id=1, account_id=11, platform="telegram",
                           address="555", text="т", state=state,
                           attempts=attempts)


def test_attempts_are_bounded_and_exhaustion_is_final():
    """Инвариант 5: исчерпав попытки, сообщение больше не берётся в прогон."""
    message = _message()
    for i in range(MAX_ATTEMPTS - 1):
        message = message.attempt_failed("timeout")
        assert message.state == "queued"
    message = message.attempt_failed("timeout")
    assert message.state == "failed" and message.attempts == MAX_ATTEMPTS


def test_a_sent_message_is_never_resent():
    """Инвариант 4."""
    with pytest.raises(AlreadySent):
        _message(state="sent").resend()


def test_manual_resend_requeues_only_the_failed_one():
    resent = _message(state="failed", attempts=MAX_ATTEMPTS).resend()
    assert resent.state == "queued" and resent.attempts == 0

    with pytest.raises(NotFailed):
        _message(state="queued").resend()


def test_only_a_queued_message_is_cancelled():
    assert _message().cancel().state == "cancelled"
    with pytest.raises(NotQueued):
        _message(state="sent").cancel()
