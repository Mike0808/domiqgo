"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий, проверка
существования чужих сущностей через их API (инвариант 4) и единственное место
модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date

from bus import publish
from modules.properties import api as properties

from ..domain.tenancy import Tenancy, Terms
from ..events import TenancyEnded, TenancyStarted
from .ports import TenancyRepository


class PropertyNotFound(LookupError):
    """Объекта с таким номером в реестре Properties нет (инвариант 4)."""


class TenancyNotFound(LookupError):
    pass


def start_tenancy(repository: TenancyRepository, property_id: int,
                  account_id: int, full_name: str, started_on: date,
                  terms: Terms) -> int:
    """Заселить. Существование объекта спрашивается у Properties; вывод из
    эксплуатации проверяет история — по признаку, полученному событием.

    Существование учётной записи не проверяется: у Identity пока нет ответа
    «такой записи нет» — `get_account` отвечает типом любому номеру. Половина
    инварианта 4 ждёт этого ответа.
    """
    if properties.get_property(property_id) is None:
        raise PropertyNotFound(f"объект #{property_id} не найден")
    history = repository.load_history(property_id)
    tenancy = history.start(Tenancy(
        tenancy_id=None, property_id=property_id, account_id=account_id,
        full_name=full_name, started_on=started_on, terms=terms))
    saved = repository.add(tenancy)
    publish(TenancyStarted(
        tenancy_id=saved.tenancy_id, property_id=property_id,
        account_id=account_id, started_on=started_on,
        rent=terms.rent, internet=terms.internet, other_fixed=terms.other_fixed))
    return saved.tenancy_id


def end_tenancy(repository: TenancyRepository, tenancy_id: int, on: date) -> None:
    """Зафиксировать выезд."""
    tenancy = repository.get(tenancy_id)
    if tenancy is None:
        raise TenancyNotFound(f"договор #{tenancy_id} не найден")
    ended = tenancy.end(on)
    repository.save(ended)
    publish(TenancyEnded(tenancy_id=tenancy_id, property_id=tenancy.property_id,
                         ended_on=on))
