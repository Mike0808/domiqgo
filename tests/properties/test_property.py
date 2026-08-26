"""Объект недвижимости — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.properties.domain import Apartment

JULY = date(2026, 7, 15)


def _apartment(decommissioned_on=None):
    return Apartment(apartment_id=1, label="кв. 1", has_cold_water=True,
                     has_hot_water=True, has_sewage=True,
                     gvs_heat_norm=Decimal("0.05229"),
                     decommissioned_on=decommissioned_on)


def test_a_new_property_is_in_service():
    assert _apartment().in_service is True


def test_a_decommissioned_property_is_not_in_service():
    assert _apartment(decommissioned_on=JULY).in_service is False


def test_decommissioning_records_the_date():
    """Датой, а не флагом: владельцу важно, с какого числа объект перестал
    сдаваться, а отчёту за прошлый год — что тогда он ещё сдавался."""
    withdrawn = _apartment().decommission(JULY)

    assert withdrawn.decommissioned_on == JULY
    assert withdrawn.in_service is False


def test_decommissioning_does_not_touch_the_original():
    """Агрегат замкнут: изменение состояния порождает новый объект. Так
    вызывающий не может изменить его мимо команды."""
    apartment = _apartment()

    apartment.decommission(JULY)

    assert apartment.in_service is True


def test_decommissioning_twice_moves_the_date():
    """Команда описывает желаемое состояние, а не переход."""
    withdrawn = _apartment(decommissioned_on=date(2026, 1, 1)).decommission(JULY)

    assert withdrawn.decommissioned_on == JULY


def test_recommissioning_clears_the_date():
    """Без возврата первая же ошибка вывода превращалась бы в тупик."""
    returned = _apartment(decommissioned_on=JULY).recommission()

    assert returned.decommissioned_on is None
    assert returned.in_service is True


def test_recommissioning_keeps_everything_else():
    returned = _apartment(decommissioned_on=JULY).recommission()

    assert (returned.label, returned.gvs_heat_norm) == ("кв. 1", Decimal("0.05229"))


def test_the_aggregate_cannot_be_edited_in_place():
    with pytest.raises(Exception):
        _apartment().label = "другое"
