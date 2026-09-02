"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий, проверка
существования чужих сущностей через их API (инвариант 4) и единственное место
модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date, timedelta

from bus import publish
from modules.properties import api as properties

from ..domain.tenancy import Tenancy, Terms
from ..domain.history import PropertyHistory
from ..events import TenancyCorrected, TenancyEnded, TenancyStarted
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


def correct_tenancy(repository: TenancyRepository, tenancy_id: int, *,
                    started_on=None, full_name=None, terms=None) -> None:
    """Исправить сведения договора; исправление даты её же подтверждает.

    Пересечение проверяется только с подтверждёнными соседями — черновики
    миграции не запирают диалог подтверждения (см. `PropertyHistory.correct`).
    Событие публикуется, только если что-то действительно изменилось;
    подтверждение предложенной даты изменением не является.
    """
    tenancy = repository.get(tenancy_id)
    if tenancy is None:
        raise TenancyNotFound(f"договор #{tenancy_id} не найден")
    corrected, changes = tenancy.correct(
        started_on=started_on, full_name=full_name, terms=terms)
    repository.load_history(tenancy.property_id).correct(corrected)
    repository.save(corrected)
    if changes:
        publish(TenancyCorrected(tenancy_id=tenancy_id,
                                 property_id=tenancy.property_id,
                                 changes=changes))


def renew_tenancy(repository: TenancyRepository, tenancy_id: int, on: date,
                  terms: Terms, full_name: str | None = None) -> int:
    """Продлить на новых условиях: завершить текущий договор днём раньше и
    открыть следующий с этой даты — одной операцией.

    Продление — новый факт, а не правка: прежний договор продолжает
    действовать в своём прошлом, и пересчёт старого месяца возьмёт прежние
    условия. Событий два — `TenancyEnded` и `TenancyStarted`: отдельного
    «условия изменились» нет намеренно (спецификация).
    """
    current = repository.get(tenancy_id)
    if current is None:
        raise TenancyNotFound(f"договор #{tenancy_id} не найден")
    ended = current.end(on - timedelta(days=1))
    successor = Tenancy(
        tenancy_id=None, property_id=current.property_id,
        account_id=current.account_id,
        full_name=current.full_name if full_name is None else full_name,
        started_on=on, terms=terms)
    history = repository.load_history(current.property_id)
    # Сначала весь план в памяти — обе записи идут только после того, как
    # домен принял и завершение, и преемника.
    PropertyHistory(
        current.property_id,
        [ended if t.tenancy_id == tenancy_id else t for t in history.tenancies],
        out_of_service=history.out_of_service,
    ).start(successor)
    repository.save(ended)
    saved = repository.add(successor)
    publish(TenancyEnded(tenancy_id=tenancy_id, property_id=current.property_id,
                         ended_on=ended.ended_on))
    publish(TenancyStarted(
        tenancy_id=saved.tenancy_id, property_id=current.property_id,
        account_id=current.account_id, started_on=on,
        rent=terms.rent, internet=terms.internet, other_fixed=terms.other_fixed))
    return saved.tenancy_id
