"""Исходящее сообщение — второй корень агрегата.

Текст фиксируется в момент постановки в очередь и позже не меняется
(инвариант 6): журнал обязан свидетельствовать о том, что человек на самом
деле получил. Здесь только stdlib.
"""

from dataclasses import dataclass, replace

#: Исчерпав попытки, сообщение переходит в «не доставлено» и больше не
#: берётся в прогон (инвариант 5).
MAX_ATTEMPTS = 5

QUEUED = "queued"
SENT = "sent"
FAILED = "failed"
CANCELLED = "cancelled"


class AlreadySent(ValueError):
    """Отправленное сообщение не отправляется повторно (инвариант 4)."""


class NotFailed(ValueError):
    """Повторная отправка вручную — только для недоставленных."""


class NotQueued(ValueError):
    """Снять с очереди можно только неотправленное."""


@dataclass(frozen=True)
class OutgoingMessage:
    message_id: int | None
    account_id: int
    platform: str
    address: str
    text: str
    state: str = QUEUED
    attempts: int = 0
    last_error: str = ""

    def delivered(self) -> "OutgoingMessage":
        return replace(self, state=SENT)

    def attempt_failed(self, error: str) -> "OutgoingMessage":
        attempts = self.attempts + 1
        state = FAILED if attempts >= MAX_ATTEMPTS else QUEUED
        return replace(self, attempts=attempts, state=state,
                       last_error=error[:300])

    def resend(self) -> "OutgoingMessage":
        """Вручную, владельцем. Отправленное не трогается (инвариант 4)."""
        if self.state == SENT:
            raise AlreadySent("Сообщение уже доставлено.")
        if self.state != FAILED:
            raise NotFailed("Повторно отправляют недоставленное; это и так в очереди.")
        return replace(self, state=QUEUED, attempts=0)

    def cancel(self) -> "OutgoingMessage":
        if self.state != QUEUED:
            raise NotQueued("С очереди снимают неотправленное.")
        return replace(self, state=CANCELLED)
