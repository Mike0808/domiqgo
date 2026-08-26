"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий и единственное
место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date

from bus import publish

from ..events import PropertyDecommissioned, PropertyRecommissioned
from .ports import PropertyRepository


class PropertyNotFound(LookupError):
    """Объекта с таким идентификатором нет."""


def _require(repository: PropertyRepository, apartment_id: int):
    apartment = repository.load(apartment_id)
    if apartment is None:
        raise PropertyNotFound(f"Объекта #{apartment_id} не существует.")
    return apartment


def decommission_property(repository: PropertyRepository, apartment_id: int,
                          on_date: date) -> None:
    """Вывести объект из эксплуатации.

    Событие публикуется всегда, включая повторный вывод: команда описывает
    желаемое состояние, а не переход, а дата вывода при повторе меняется — и
    подписчик обязан узнать именно новую.
    """
    apartment = _require(repository, apartment_id).decommission(on_date)
    repository.save_service_state(apartment)
    publish(PropertyDecommissioned(apartment_id=apartment_id,
                                   decommissioned_on=on_date))


def recommission_property(repository: PropertyRepository,
                          apartment_id: int) -> None:
    """Вернуть объект в эксплуатацию.

    Возврат уже действующего объекта не объявляется: ничего не произошло, а
    подписчик (Tenancy) снимал бы запрет, которого не ставил.
    """
    apartment = _require(repository, apartment_id)
    if apartment.in_service:
        return
    repository.save_service_state(apartment.recommission())
    publish(PropertyRecommissioned(apartment_id=apartment_id))
