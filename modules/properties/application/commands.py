"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий и единственное
место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date
from decimal import Decimal

from bus import publish

from ..events import (
    PropertyDecommissioned, PropertyRecommissioned, PropertyRegistered,
    PropertyServiceCompositionChanged,
)
from ..domain.property import ensure_heat_norm_is_set, ensure_label_is_set
from .ports import PropertyRepository


class PropertyNotFound(LookupError):
    """Объекта с таким идентификатором нет."""


def _require(repository: PropertyRepository, apartment_id: int):
    apartment = repository.load(apartment_id)
    if apartment is None:
        raise PropertyNotFound(f"Объекта #{apartment_id} не существует.")
    return apartment


def register_property(repository: PropertyRepository, label: str,
                      address: str = "", has_cold_water: bool = True,
                      has_hot_water: bool = True, has_sewage: bool = True,
                      gvs_heat_norm=Decimal("0")) -> int:
    """Завести объект. Возвращает идентификатор заведённого.

    Инварианты проверяются до записи: объект без наименования и объект с
    подведённой ГВС без норматива не должны существовать даже мгновение.
    """
    ensure_label_is_set(label)
    ensure_heat_norm_is_set(has_hot_water, gvs_heat_norm)
    apartment_id = repository.create(label.strip(), address.strip(),
                                     has_cold_water, has_hot_water,
                                     has_sewage, gvs_heat_norm)
    publish(PropertyRegistered(apartment_id=apartment_id, label=label.strip()))
    return apartment_id


def rename_property(repository: PropertyRepository, apartment_id: int,
                    label: str, address: str = "") -> None:
    """Изменить наименование или адрес.

    События нет: спецификация его не заводит, и заводить нечего — ни одно
    правило системы не зависит от того, как владелец назвал квартиру.
    """
    apartment = _require(repository, apartment_id).rename(label, address)
    repository.save_description(apartment)


def change_service_composition(repository: PropertyRepository,
                               apartment_id: int, has_cold_water: bool,
                               has_hot_water: bool, has_sewage: bool,
                               gvs_heat_norm) -> None:
    """Изменить состав подведённых услуг и норматив подогрева.

    Событие публикуется только если состав действительно изменился: сохранение
    формы без правок — не факт предметной области.
    """
    was = _require(repository, apartment_id)
    now = was.change_service_composition(has_cold_water, has_hot_water,
                                         has_sewage, gvs_heat_norm)
    if now == was:
        return
    repository.save_description(now)
    publish(PropertyServiceCompositionChanged(
        apartment_id=apartment_id,
        was_cold_water=was.has_cold_water, was_hot_water=was.has_hot_water,
        was_sewage=was.has_sewage, now_cold_water=now.has_cold_water,
        now_hot_water=now.has_hot_water, now_sewage=now.has_sewage,
        previous_heat_norm=was.gvs_heat_norm, new_heat_norm=now.gvs_heat_norm,
    ))


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
