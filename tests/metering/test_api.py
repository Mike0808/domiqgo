"""Публичная поверхность Metering: реестр приборов, показания, расход.

Здесь проверяется связка целиком — от api до таблицы. Сами правила (база
отсчёта, монотонность) проверяются без базы в `test_point.py`: дублировать их
здесь значило бы проверять домен через хранилище, ради чего он и отделён.

Перезапись комплекта при повторной сдаче сохранена дословно с шага C2c:
ограничения на неё — замок периода — приезжают на C2g.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.metering import api
from modules.metering.infrastructure.models import Meter, MeterReading

pytestmark = pytest.mark.django_db

JULY = date(2026, 7, 1)
JUNE = date(2026, 6, 1)
APARTMENT = 1
NEIGHBOUR = 2


def _meter(resource="cold_water", apartment_id=APARTMENT, serial="", initial="0"):
    return Meter.objects.create(apartment_id=apartment_id, resource=resource,
                                serial_number=serial,
                                initial_value=Decimal(initial))


def _reading(resource="cold_water", period=JULY, value="100",
             apartment_id=APARTMENT):
    return MeterReading.objects.create(apartment_id=apartment_id, period=period,
                                       resource=resource, value=Decimal(value))


# ------------------------------------------------------------ реестр приборов

def test_expected_meters_returns_the_registry_of_the_point():
    _meter("cold_water", serial="CW-1", initial="100")

    meters = api.get_expected_meters(APARTMENT)

    assert [(m.resource, m.serial_number, m.initial_value) for m in meters] == [
        ("cold_water", "CW-1", Decimal("100.000"))]


def test_expected_meters_is_empty_for_a_point_without_meters():
    assert api.get_expected_meters(APARTMENT) == []


def test_expected_meters_does_not_leak_between_points():
    _meter("cold_water", apartment_id=APARTMENT)
    _meter("electricity_single", apartment_id=NEIGHBOUR)

    assert [m.resource for m in api.get_expected_meters(APARTMENT)] == ["cold_water"]


def test_a_meter_crosses_the_border_without_django():
    """Наружу уезжает замкнутый датакласс, а не модель: вызывающему незачем
    знать ни про ORM, ни про внутренности модуля (правила 1.1 и 1.2)."""
    _meter()

    record = api.get_expected_meters(APARTMENT)[0]

    assert not hasattr(record, "save")
    with pytest.raises(Exception):
        record.resource = "hot_water"


# ----------------------------------------------------------------- показания

def test_readings_returns_the_set_for_the_period():
    _reading("cold_water", JULY, "110")
    _reading("electricity_single", JULY, "1500")

    assert api.get_readings(APARTMENT, JULY) == {
        "cold_water": Decimal("110.000"),
        "electricity_single": Decimal("1500.000")}


def test_readings_of_another_period_are_not_returned():
    _reading("cold_water", JUNE, "100")

    assert api.get_readings(APARTMENT, JULY) == {}


def test_readings_of_another_point_are_not_returned():
    _reading("cold_water", JULY, "999", apartment_id=NEIGHBOUR)

    assert api.get_readings(APARTMENT, JULY) == {}


# ------------------------------------------------------------------- расход

def test_consumption_counts_from_the_previous_period():
    _meter("cold_water", initial="0")
    _reading("cold_water", JUNE, "100")
    _reading("cold_water", JULY, "110")

    used = api.get_consumption(APARTMENT, JULY, ["cold_water"])

    assert used["cold_water"].used == Decimal("10.000")


def test_consumption_of_the_first_month_counts_from_the_act():
    """Показаний ещё не сдавали — базой становится начальное значение
    прибора, зафиксированное при подписании договора."""
    _meter("cold_water", initial="100")
    _reading("cold_water", JULY, "110")

    used = api.get_consumption(APARTMENT, JULY, ["cold_water"])

    assert used["cold_water"].used == Decimal("10.000")


def test_consumption_does_not_take_a_neighbours_reading_as_the_baseline():
    _meter("cold_water", initial="100")
    _reading("cold_water", JUNE, "999", apartment_id=NEIGHBOUR)
    _reading("cold_water", JULY, "110")

    used = api.get_consumption(APARTMENT, JULY, ["cold_water"])

    assert used["cold_water"].baseline == Decimal("100.000")


def test_consumption_refuses_without_a_baseline():
    _reading("cold_water", JULY, "110")

    with pytest.raises(api.BaselineMissing):
        api.get_consumption(APARTMENT, JULY, ["cold_water"])


def test_consumption_refuses_a_backward_reading():
    _meter("cold_water", initial="0")
    _reading("cold_water", JUNE, "100")
    _reading("cold_water", JULY, "90")

    with pytest.raises(api.ReadingWentBackwards):
        api.get_consumption(APARTMENT, JULY, ["cold_water"])


# ------------------------------------------------------------ сдача комплекта

def test_submitting_stores_the_whole_set():
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110"),
                                          "electricity_single": Decimal("1500")})

    assert api.get_readings(APARTMENT, JULY) == {
        "cold_water": Decimal("110.000"),
        "electricity_single": Decimal("1500.000")}


def test_resubmitting_overwrites_instead_of_adding_a_second_row():
    """Поведение до переезда сохранено дословно: повторная сдача правит
    строку. Ограничения на перезапись — замок периода — приезжают на C2g."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("120")})

    assert MeterReading.objects.filter(resource="cold_water").count() == 1
    assert api.get_readings(APARTMENT, JULY) == {"cold_water": Decimal("120.000")}


def test_submitting_does_not_touch_another_period():
    _reading("cold_water", JUNE, "100")

    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    assert api.get_readings(APARTMENT, JUNE) == {"cold_water": Decimal("100.000")}


def test_submitting_does_not_touch_another_point():
    _reading("cold_water", JULY, "999", apartment_id=NEIGHBOUR)

    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    assert api.get_readings(NEIGHBOUR, JULY) == {"cold_water": Decimal("999.000")}


def test_the_author_of_the_entry_is_recorded():
    """Различать, кто внёс показание, нужно владельцу: своё исправление он
    должен отличать от сданного жильцом."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")},
                        entered_by_tenant=True)

    assert MeterReading.objects.get().entered_by_tenant is True


def test_resubmitting_updates_the_author_too():
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")},
                        entered_by_tenant=False)
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("120")},
                        entered_by_tenant=True)

    assert MeterReading.objects.get().entered_by_tenant is True


def test_an_unknown_resource_is_refused_at_the_boundary():
    with pytest.raises(api.UnknownResource):
        api.submit_readings(APARTMENT, JULY, {"sewage": Decimal("10")})


def test_a_refused_set_stores_nothing():
    """Комплект сдаётся целиком: одно негодное значение не должно оставить
    половину записанной."""
    with pytest.raises(api.UnknownResource):
        api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110"),
                                              "sewage": Decimal("10")})

    assert MeterReading.objects.count() == 0


# ------------------------------------------------------------ есть ли история

def test_has_meters_and_has_readings_answer_per_point():
    _meter("cold_water", apartment_id=APARTMENT)
    _reading("cold_water", JULY, "110", apartment_id=NEIGHBOUR)

    assert api.has_meters(APARTMENT) is True
    assert api.has_readings(APARTMENT) is False
    assert api.has_meters(NEIGHBOUR) is False
    assert api.has_readings(NEIGHBOUR) is True


def test_an_empty_point_has_no_history():
    assert api.has_meters(APARTMENT) is False
    assert api.has_readings(APARTMENT) is False
