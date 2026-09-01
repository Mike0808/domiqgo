"""Порты хранилищ: согласий, кодов привязки и привязанных провайдеров."""

from datetime import datetime
from typing import Protocol

from ..domain.link_code import LinkCode


class ConsentRepository(Protocol):
    def load_journal(self, account_id: int): ...

    def append(self, account_id: int, policy_version: str,
               given_at: datetime) -> None: ...


class LinkCodeRepository(Protocol):
    def replace(self, link_code: LinkCode) -> None:
        """Сделать этот код единственным действующим у его учётной записи."""

    def find(self, code: str) -> LinkCode | None: ...

    def discard(self, link_code: LinkCode) -> None:
        """Погасить: после этого `find` его не находит."""


class LinkedProviders(Protocol):
    def linked_providers(self, account_id: int) -> list[str]:
        """Идентификаторы провайдеров, привязанных к записи."""
