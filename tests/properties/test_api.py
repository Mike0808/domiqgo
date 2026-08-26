"""Публичная поверхность Properties: чтение объекта, вывод из эксплуатации.

`transaction=True`: команды публикуют события, а шина доставляет после
фиксации.
"""

from datetime import date
from decimal import Decimal

import pytest

from bus import clear_subscribers, subscribe
from modules.properties import api
from modules.properties.events import (
    PropertyDecommissioned, PropertyRecommissioned,
)
from modules.properties.infrastructure.models import Apartment

pytestmark = pytest.mark.django_db(transaction=True)

JULY = date(2026, 7, 15)


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def received():
    events = []
    for event_type in (PropertyDecommissioned, PropertyRecommissioned):
        subscribe(event_type, events.append)
    return events


def _apartment(label="кв. 1", **fields):
    return Apartment.objects.create(label=label, **fields)


# ------------------------------------------------------------------- запросы

def test_get_property_returns_the_object_without_django():
    """Наружу уезжает замкнутый датакласс, а не модель: вызывающему незачем
    знать ни про ORM, ни про внутренности модуля."""
    apartment = _apartment(gvs_heat_norm=Decimal("0.05229"))

    found = api.get_property(apartment.pk)

    assert (found.label, found.gvs_heat_norm) == ("кв. 1", Decimal("0.05229"))
    assert not hasattr(found, "save")


def test_get_property_returns_none_when_there_is_no_such_object():
    assert api.get_property(404) is None


def test_get_property_carries_the_service_composition():
    """Состав подведённых услуг — то, ради чего Billing и спрашивает объект."""
    apartment = _apartment(has_hot_water=False, has_sewage=False)

    found = api.get_property(apartment.pk)

    assert (found.has_cold_water, found.has_hot_water, found.has_sewage) == (
        True, False, False)


def test_listing_hides_decommissioned_objects():
    """Иначе список владельца с годами зарастает проданными квартирами."""
    _apartment("действует")
    sold = _apartment("продана")
    api.decommission_property(sold.pk, JULY)

    assert [a.label for a in api.list_properties()] == ["действует"]


def test_listing_can_include_decommissioned_objects():
    sold = _apartment("продана")
    api.decommission_property(sold.pk, JULY)

    assert [a.label for a in api.list_properties(include_decommissioned=True)] == [
        "продана"]


def test_listing_is_ordered_by_label():
    _apartment("Б")
    _apartment("А")

    assert [a.label for a in api.list_properties()] == ["А", "Б"]


# ------------------------------------------------------------------- команды

def test_decommissioning_stores_the_date(received):
    apartment = _apartment()

    api.decommission_property(apartment.pk, JULY)

    assert api.get_property(apartment.pk).decommissioned_on == JULY


def test_decommissioning_announces_it(received):
    apartment = _apartment()

    api.decommission_property(apartment.pk, JULY)

    event = received[0]
    assert isinstance(event, PropertyDecommissioned)
    assert (event.apartment_id, event.decommissioned_on) == (apartment.pk, JULY)


def test_decommissioning_twice_announces_the_new_date(received):
    """Команда описывает желаемое состояние, а не переход; дата при повторе
    меняется, и подписчик обязан узнать именно новую."""
    apartment = _apartment()
    api.decommission_property(apartment.pk, date(2026, 1, 1))
    received.clear()

    api.decommission_property(apartment.pk, JULY)

    assert received[0].decommissioned_on == JULY


def test_recommissioning_returns_the_object(received):
    apartment = _apartment()
    api.decommission_property(apartment.pk, JULY)

    api.recommission_property(apartment.pk)

    assert api.get_property(apartment.pk).in_service is True


def test_recommissioning_announces_it(received):
    apartment = _apartment()
    api.decommission_property(apartment.pk, JULY)
    received.clear()

    api.recommission_property(apartment.pk)

    assert [type(e) for e in received] == [PropertyRecommissioned]


def test_recommissioning_an_object_in_service_announces_nothing(received):
    """Ничего не произошло, а подписчик снимал бы запрет, которого не ставил."""
    apartment = _apartment()

    api.recommission_property(apartment.pk)

    assert received == []


def test_a_command_on_a_missing_object_is_refused(received):
    with pytest.raises(api.PropertyNotFound):
        api.decommission_property(404, JULY)

    assert received == []


def test_decommissioning_one_leaves_the_neighbour_in_service():
    apartment = _apartment("кв. 1")
    neighbour = _apartment("кв. 2")

    api.decommission_property(apartment.pk, JULY)

    assert api.get_property(neighbour.pk).in_service is True


def test_the_fields_of_other_modules_survive_a_command():
    """В таблице лежат временные жильцы — арендная ставка, интернет, политика
    округления. Запись состояния эксплуатации не смеет их затирать: домен о
    них не знает и восстановить бы не смог."""
    apartment = _apartment(rent=Decimal("20000"), internet=Decimal("700"),
                           round_total=False)

    api.decommission_property(apartment.pk, JULY)

    stored = Apartment.objects.get(pk=apartment.pk)
    assert stored.rent == Decimal("20000")
    assert stored.internet == Decimal("700")
    assert stored.round_total is False


# -------------------------------------------------------------------- журнал

def test_both_commands_land_in_the_journal():
    from bus.models import PublishedEvent

    apartment = _apartment()
    api.decommission_property(apartment.pk, JULY)
    api.recommission_property(apartment.pk)

    recorded = [e.event_type.rsplit(".", 1)[-1] for e in PublishedEvent.objects.all()]
    assert recorded == ["PropertyDecommissioned", "PropertyRecommissioned"]
