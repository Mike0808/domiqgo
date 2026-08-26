"""События Metering: что модуль объявляет и когда.

`transaction=True` во всём файле: события доставляются после фиксации, которой
под обычным `django_db` не происходит никогда
(`tests/bus/test_bus.py::test_events_never_arrive_under_the_default_db_mark`).

Подписчиков у этих событий на шаге C2f нет: пересчёт счёта делает вызывающий,
синхронно, и переезд на подписку — часть шага E4. Проверяется поэтому сам
контракт: что объявлено, с какой нагрузкой и в какой момент.
"""

from datetime import date
from decimal import Decimal

import pytest

from bus import clear_subscribers, subscribe
from modules.metering import api
from modules.metering.events import (
    MeterReadingCorrected, MeterReadingsSubmitted, MeterRegistered,
)
from modules.metering.infrastructure.models import MeterReading

pytestmark = pytest.mark.django_db(transaction=True)

JULY = date(2026, 7, 1)
APARTMENT = 1


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def received():
    """Подписка на все три события модуля."""
    events = []
    for event_type in (MeterReadingsSubmitted, MeterReadingCorrected,
                       MeterRegistered):
        subscribe(event_type, events.append)
    return events


# ----------------------------------------------------------- ввод в учёт

def test_registering_a_meter_announces_it(received):
    api.register_meter(APARTMENT, "cold_water", Decimal("100"),
                       serial_number="CW-1", initial_date=date(2026, 1, 15))

    event = received[0]
    assert isinstance(event, MeterRegistered)
    assert (event.apartment_id, event.resource, event.serial_number) == (
        APARTMENT, "cold_water", "CW-1")
    assert event.initial_value == Decimal("100")
    assert event.initial_date == date(2026, 1, 15)


def test_a_meter_of_an_unknown_resource_is_refused_and_announces_nothing(received):
    with pytest.raises(api.UnknownResource):
        api.register_meter(APARTMENT, "sewage", Decimal("0"))

    assert received == []


# ------------------------------------------------------------ сдача комплекта

def test_submitting_announces_the_whole_set_at_once(received):
    """Событие на транзакцию, а не на строку: иначе подписчик пересчитал бы
    счёт трижды подряд, причём дважды — по неполным данным."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110"),
                                          "electricity_single": Decimal("1500")},
                        entered_by_tenant=True)

    assert len(received) == 1
    event = received[0]
    assert isinstance(event, MeterReadingsSubmitted)
    assert (event.apartment_id, event.period) == (APARTMENT, JULY)
    assert event.resources == ("cold_water", "electricity_single")
    assert event.entered_by_tenant is True


def test_the_author_travels_with_the_set(received):
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")},
                        entered_by_tenant=False)

    assert received[0].entered_by_tenant is False


def test_an_empty_set_announces_nothing(received):
    """Сдавать нечего — не событие. Пустой комплект приходит от квартиры без
    заведённых приборов, и объявлять о нём означало бы будить подписчиков на
    пустом месте."""
    api.submit_readings(APARTMENT, JULY, {})

    assert received == []


def test_a_refused_set_announces_nothing(received):
    with pytest.raises(api.UnknownResource):
        api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110"),
                                              "sewage": Decimal("10")})

    assert received == []


# --------------------------------------------------------------- исправление

def test_correcting_announces_both_values(received):
    """Прежнее значение едет в нагрузке: подписчик должен понять масштаб
    расхождения, не обращаясь обратно в Metering."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    received.clear()

    api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    event = received[0]
    assert isinstance(event, MeterReadingCorrected)
    assert event.previous_value == Decimal("110.000")
    assert event.new_value == Decimal("115")


def test_correcting_does_not_announce_a_submission(received):
    """Сдача и исправление — разные события: на выставленный счёт они влияют
    по-разному, и подписчик обязан их различать."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    received.clear()

    api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    assert [type(e) for e in received] == [MeterReadingCorrected]


def test_correcting_a_reading_that_was_never_submitted_is_refused(received):
    api.register_meter(APARTMENT, "cold_water", Decimal("0"))
    received.clear()

    with pytest.raises(api.ReadingNotFound):
        api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    assert received == []
    assert MeterReading.objects.count() == 0


def test_a_correction_replaces_the_value_without_adding_a_row():
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    assert MeterReading.objects.count() == 1
    assert api.get_readings(APARTMENT, JULY) == {"cold_water": Decimal("115.000")}


# -------------------------------------------------------------------- журнал

def test_every_command_lands_in_the_journal():
    from bus.models import PublishedEvent

    api.register_meter(APARTMENT, "cold_water", Decimal("0"))
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    recorded = [e.event_type.rsplit(".", 1)[-1] for e in PublishedEvent.objects.all()]
    assert recorded == ["MeterRegistered", "MeterReadingsSubmitted",
                        "MeterReadingCorrected"]


def test_the_journal_keeps_the_resource_list_as_data():
    """Кортеж ресурсов обязан пережить сериализацию: журнал — источник для
    пересборки проекций, и нагрузка в нём должна читаться обратно."""
    from bus.models import PublishedEvent

    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110"),
                                          "electricity_single": Decimal("1500")})

    payload = PublishedEvent.objects.get().payload
    assert payload["resources"] == ["cold_water", "electricity_single"]
