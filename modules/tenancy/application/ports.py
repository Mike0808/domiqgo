"""Порт хранилища договоров."""

from datetime import date
from typing import Protocol

from ..domain.history import PropertyHistory
from ..domain.tenancy import Tenancy


class TenancyRepository(Protocol):
    def load_history(self, property_id: int) -> PropertyHistory:
        """Все договоры объекта и признак вывода из эксплуатации."""

    def add(self, tenancy: Tenancy) -> Tenancy:
        """Сохранить новый договор и вернуть его с номером."""

    def save(self, tenancy: Tenancy) -> None:
        """Записать изменившийся договор (дата выезда, подтверждение)."""

    def get(self, tenancy_id: int) -> Tenancy | None: ...

    def active_for_account(self, account_id: int, day: date) -> Tenancy | None:
        """Договор учётной записи, действующий в этот день."""

    def list_for_account(self, account_id: int) -> list[Tenancy]:
        """Все договоры записи, от ранних к поздним."""

    def mark_out_of_service(self, property_id: int, out: bool) -> None:
        """Запомнить факт из события Properties."""
