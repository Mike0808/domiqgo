"""Публичная поверхность Tariffs: команды, запросы, события.

`transaction=True` во всём файле: команды публикуют события, а шина доставляет
после фиксации, которой под обычным `django_db` не происходит никогда
(`tests/bus/test_bus.py::test_events_never_arrive_under_the_default_db_mark`).
"""

from datetime import date
from decimal import Decimal

import pytest

from bus import clear_subscribers, subscribe
from modules.tariffs import api
from modules.tariffs.events import (
    TariffVersionCorrected, TariffVersionPublished, TariffVersionWithdrawn,
)

pytestmark = pytest.mark.django_db(transaction=True)

JULY = date(2026, 7, 1)
JANUARY = date(2026, 1, 1)


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def received():
    """Подписка на все три события модуля."""
    events = []
    for event_type in (TariffVersionPublished, TariffVersionCorrected,
                       TariffVersionWithdrawn):
        subscribe(event_type, events.append)
    return events


# ------------------------------------------------------------------- запросы

def test_rate_on_returns_the_version_effective_on_that_date():
    api.publish_tariff_version("cold_water", Decimal("40.00"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    assert api.get_rate_on("cold_water", date(2026, 6, 30)).rate == Decimal("40.00")
    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")


def test_rate_on_returns_none_when_there_is_no_rate():
    assert api.get_rate_on("cold_water", JULY) is None


def test_rates_on_answers_for_every_utility_at_once():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    api.publish_tariff_version("electricity_single", Decimal("4.87"), JANUARY)
    api.publish_tariff_version("sewage", Decimal("36.40"), date(2027, 1, 1))  # будущая

    rates = api.get_rates_on(JULY)

    assert set(rates) == {"cold_water", "electricity_single"}
    assert rates["electricity_single"].rate == Decimal("4.87")


def test_rates_on_picks_the_latest_version_per_utility():
    api.publish_tariff_version("cold_water", Decimal("40.00"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    assert api.get_rates_on(JULY)["cold_water"].rate == Decimal("48.15")


def test_rates_on_is_empty_when_nothing_is_published():
    assert api.get_rates_on(JULY) == {}


def test_list_versions_returns_the_whole_history_in_order():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    api.publish_tariff_version("cold_water", Decimal("40.00"), JANUARY)

    assert [v.effective_from for v in api.list_versions("cold_water")] == [JANUARY, JULY]


def test_source_travels_with_the_rate():
    """Реквизиты первоисточника — то, что делает цифру проверяемой для жильца."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY,
                               source_name="Постановление 123",
                               source_url="https://example/1")

    rate = api.get_rate_on("cold_water", JULY)
    assert rate.source_name == "Постановление 123"
    assert rate.source_url == "https://example/1"


def test_unknown_utility_is_refused_at_the_boundary():
    with pytest.raises(api.UnknownUtility):
        api.publish_tariff_version("hot_water", Decimal("1"), JULY)


# ------------------------------------------------------------------- команды

def test_correct_changes_the_rate_without_adding_a_version():
    api.publish_tariff_version("cold_water", Decimal("4.85"), JULY)

    api.correct_tariff_version("cold_water", JULY, rate=Decimal("48.15"))

    assert len(api.list_versions("cold_water")) == 1
    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")


def test_withdraw_removes_the_version():
    api.publish_tariff_version("cold_water", Decimal("40.00"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    api.withdraw_tariff_version("cold_water", JULY)

    assert api.get_rate_on("cold_water", JULY).rate == Decimal("40.00")


def test_withdrawing_the_last_version_leaves_the_utility_without_a_rate():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    api.withdraw_tariff_version("cold_water", JULY)

    assert api.get_rate_on("cold_water", JULY) is None


def test_one_utility_does_not_disturb_another():
    """Репозиторий переписывает линию целиком — проверка, что «целиком»
    ограничено одной услугой."""
    api.publish_tariff_version("electricity_single", Decimal("4.87"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    api.correct_tariff_version("cold_water", JULY, rate=Decimal("50.00"))

    assert api.get_rate_on("electricity_single", JANUARY).rate == Decimal("4.87")


# ------------------------------------------------------------------- события

def test_publishing_a_version_announces_it(received):
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY,
                               source_name="Постановление 123")

    assert len(received) == 1
    event = received[0]
    assert isinstance(event, TariffVersionPublished)
    assert (event.utility, event.rate, event.effective_from) == (
        "cold_water", Decimal("48.15"), JULY)
    assert event.source_name == "Постановление 123"


def test_correction_carries_both_rates_and_the_affected_range(received):
    """Отрезок в payload — де-факто контракт: по ADR-0005 Billing помечает
    затронутые счета сам и обращаться обратно в Tariffs не должен."""
    api.publish_tariff_version("cold_water", Decimal("4.85"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    received.clear()

    api.correct_tariff_version("cold_water", JANUARY, rate=Decimal("40.00"))

    event = received[0]
    assert isinstance(event, TariffVersionCorrected)
    assert event.previous_rate == Decimal("4.85")
    assert event.new_rate == Decimal("40.00")
    assert (event.effective_from, event.effective_until) == (JANUARY, JULY)


def test_correcting_the_last_version_leaves_the_range_open(received):
    api.publish_tariff_version("cold_water", Decimal("4.85"), JULY)
    received.clear()

    api.correct_tariff_version("cold_water", JULY, rate=Decimal("48.15"))

    assert received[0].effective_until is None


def test_moving_a_version_reports_the_new_range_not_the_old(received):
    """Отрезок снимается после правки: если исправляли дату, затронут новый
    отрезок, а не прежний."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), date(2026, 7, 11))
    received.clear()

    api.correct_tariff_version("cold_water", date(2026, 7, 11), effective_from=JULY)

    assert received[0].effective_from == JULY


def test_moving_a_version_past_another_reports_the_new_neighbour(received):
    """Тот же снимок отрезка с другого конца: версия переехала за соседнюю и
    стала последней, значит и конец отрезка теперь открыт."""
    api.publish_tariff_version("cold_water", Decimal("40.00"), JANUARY)
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    received.clear()

    api.correct_tariff_version("cold_water", JANUARY,
                               effective_from=date(2026, 8, 1))

    assert received[0].effective_until is None


def test_withdrawal_announces_what_was_removed(received):
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    received.clear()

    api.withdraw_tariff_version("cold_water", JULY)

    event = received[0]
    assert isinstance(event, TariffVersionWithdrawn)
    assert (event.utility, event.effective_from, event.withdrawn_rate) == (
        "cold_water", JULY, Decimal("48.15"))


def test_every_command_lands_in_the_journal():
    """События Tariffs — первые настоящие в проекте, и журнал шага B2 должен
    их принять."""
    from bus.models import PublishedEvent

    api.publish_tariff_version("cold_water", Decimal("4.85"), JULY)
    api.correct_tariff_version("cold_water", JULY, rate=Decimal("48.15"))
    api.withdraw_tariff_version("cold_water", JULY)

    recorded = [e.event_type.rsplit(".", 1)[-1] for e in PublishedEvent.objects.all()]
    assert recorded == ["TariffVersionPublished", "TariffVersionCorrected",
                        "TariffVersionWithdrawn"]


def test_a_failed_command_publishes_nothing(received):
    with pytest.raises(api.VersionNotFound):
        api.withdraw_tariff_version("cold_water", JULY)

    assert received == []
