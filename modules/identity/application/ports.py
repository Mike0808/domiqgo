"""Порт хранилища согласий."""

from datetime import datetime
from typing import Protocol


class ConsentRepository(Protocol):
    def load_journal(self, account_id: int): ...

    def append(self, account_id: int, policy_version: str,
               given_at: datetime) -> None: ...
