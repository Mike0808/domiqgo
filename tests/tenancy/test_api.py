"""Публичная поверхность Tenancy.

`transaction=True`: команды публикуют события, а шина доставляет после
фиксации.
"""

from datetime import date
from decimal import Decimal

import pytest

from bus import clear_subscribers, publish, subscribe
from modules.properties import api as properties
from modules.properties.events import PropertyDecommissioned, PropertyRecommissioned
from modules.tenancy import api
from modules.tenancy.application import subscriptions
from modules.tenancy.events import TenancyEnded, TenancyStarted
from modules.tenancy.infrastructure import repository

pytestmark = pytest.mark.django_db(transaction=True)

TERMS = api.Terms(rent=Decimal("30000"), internet=Decimal("500"), other_fixed=Decimal("0"))
IVANOV, PETROV = 11, 12


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def flat():
    return properties.register_property("кв", has_hot_water=False)


@pytest.fixture
def received():
    events = []
    subscribe(TenancyStarted, events.append)
    subscribe(TenancyEnded, events.append)
    return events


def test_starting_a_tenancy_records_it_and_tells_the_world(flat, received):
    tenancy_id = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)

    tenancy = api.get_tenancy(tenancy_id)
    assert tenancy.account_id == IVANOV and tenancy.terms == TERMS and tenancy.is_open
    assert received == [TenancyStarted(
        tenancy_id=tenancy_id, property_id=flat, account_id=IVANOV,
        started_on=date(2026, 3, 1), rent=Decimal("30000"),
        internet=Decimal("500"), other_fixed=Decimal("0"))]


def test_a_tenancy_needs_an_existing_property():
    with pytest.raises(api.PropertyNotFound):
        api.start_tenancy(10**6, IVANOV, "Иванов", date(2026, 3, 1), TERMS)


def test_ending_a_tenancy_frees_the_property_from_the_next_day(flat, received):
    tenancy_id = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)
    api.end_tenancy(tenancy_id, date(2026, 6, 30))

    assert received[-1] == TenancyEnded(tenancy_id=tenancy_id, property_id=flat,
                                        ended_on=date(2026, 6, 30))
    assert api.tenancy_for(flat, date(2026, 7, 1)) is None
    api.start_tenancy(flat, PETROV, "Петров", date(2026, 7, 1), TERMS)


def test_a_second_tenancy_on_the_same_days_is_refused(flat):
    api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)
    with pytest.raises(api.PeriodOverlap):
        api.start_tenancy(flat, PETROV, "Петров", date(2026, 5, 1), TERMS)


def test_the_tenancy_of_record_is_the_one_on_the_first_of_the_month(flat):
    """ADR-0024, через API."""
    first = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 1, 1), TERMS)
    api.end_tenancy(first, date(2026, 3, 5))
    second = api.start_tenancy(flat, PETROV, "Петров", date(2026, 3, 6), TERMS)

    assert api.tenancy_for(flat, date(2026, 3, 1)).tenancy_id == first
    assert api.tenancy_for(flat, date(2026, 4, 1)).tenancy_id == second
    assert [t.tenancy_id for t in api.list_tenancies_for(flat)] == [first, second]


def test_a_signed_in_tenant_is_shown_their_running_tenancy(flat):
    tenancy_id = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)

    assert api.active_tenancy_for_account(IVANOV, date(2026, 9, 1)).tenancy_id == tenancy_id
    assert api.active_tenancy_for_account(IVANOV, date(2026, 2, 1)) is None
    assert api.active_tenancy_for_account(PETROV, date(2026, 9, 1)) is None


# ------------------------------------------------- события Properties

def test_a_decommissioned_property_refuses_new_tenancies_by_event(flat):
    subscriptions.wire(repository)
    publish(PropertyDecommissioned(apartment_id=flat, decommissioned_on=date(2026, 8, 1)))

    with pytest.raises(api.PropertyOutOfService):
        api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 9, 1), TERMS)

    publish(PropertyRecommissioned(apartment_id=flat))
    api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 9, 1), TERMS)


def test_decommissioning_leaves_the_running_tenancy_alone(flat):
    subscriptions.wire(repository)
    tenancy_id = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)
    publish(PropertyDecommissioned(apartment_id=flat, decommissioned_on=date(2026, 8, 1)))

    assert api.get_tenancy(tenancy_id).is_open
    assert api.tenancy_for(flat, date(2026, 9, 1)).tenancy_id == tenancy_id


def test_the_real_decommission_command_reaches_tenancy(flat):
    """Не подделка события, а команда Properties целиком: подписка,
    установленная приложением, доставляет её сюда."""
    subscriptions.wire(repository)
    properties.decommission_property(flat, date(2026, 8, 1))

    with pytest.raises(api.PropertyOutOfService):
        api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 9, 1), TERMS)


# ------------------------------------------ исправление и продление (D2)

def test_correcting_the_proposed_date_confirms_the_draft(flat):
    from billing.tests.tenancies import draft as make_draft

    class _Flat:  # черновик, как его оставила миграция D1a
        pk = flat
    draft_id = make_draft(_Flat, 11, started_on=date(2026, 9, 1))

    api.correct_tenancy(draft_id, started_on=date(2026, 3, 1))

    corrected = api.get_tenancy(draft_id)
    assert corrected.start_confirmed and corrected.started_on == date(2026, 3, 1)


def test_a_correction_tells_the_world_what_changed(flat, received):
    from modules.tenancy.events import TenancyCorrected
    events = []
    subscribe(TenancyCorrected, events.append)
    tenancy_id = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 3, 1), TERMS)

    api.correct_tenancy(tenancy_id, terms=api.Terms(rent=Decimal("35000")))

    (event,) = events
    assert (event.tenancy_id, event.property_id) == (tenancy_id, flat)
    assert [c.split(":")[0] for c in event.changes] == ["rent", "internet"]
    assert "35000" in event.changes[0]


def test_confirming_without_changes_is_not_a_correction(flat):
    """Событие — только про изменение; подтверждение им не является."""
    from modules.tenancy.events import TenancyCorrected
    from billing.tests.tenancies import draft as make_draft
    events = []
    subscribe(TenancyCorrected, events.append)

    class _Flat:
        pk = flat
    draft_id = make_draft(_Flat, 11, started_on=date(2026, 9, 1))
    api.correct_tenancy(draft_id, started_on=date(2026, 9, 1))

    assert api.get_tenancy(draft_id).start_confirmed and events == []


def test_only_one_date_of_a_crowded_flat_can_be_confirmed(flat):
    """Квартира с двумя жильцами: первый подтверждает, второй ждёт D3."""
    from billing.tests.tenancies import draft as make_draft

    class _Flat:
        pk = flat
    first = make_draft(_Flat, 11, started_on=date(2026, 9, 1))
    second = make_draft(_Flat, 12, started_on=date(2026, 9, 1))
    api.correct_tenancy(first, started_on=date(2026, 9, 1))

    with pytest.raises(api.PeriodOverlap):
        api.correct_tenancy(second, started_on=date(2026, 9, 1))


def test_renewal_ends_the_old_contract_the_day_before(flat, received):
    old = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 1, 1), TERMS)

    new = api.renew_tenancy(old, date(2026, 7, 1), api.Terms(rent=Decimal("35000")))

    assert api.get_tenancy(old).ended_on == date(2026, 6, 30)
    assert api.tenancy_for(flat, date(2026, 6, 1)).terms.rent == Decimal("30000")
    assert api.tenancy_for(flat, date(2026, 7, 1)).terms.rent == Decimal("35000")
    assert api.get_tenancy(new).account_id == IVANOV
    assert [type(e).__name__ for e in received[-2:]] == ["TenancyEnded", "TenancyStarted"]


def test_renewal_of_an_ended_contract_is_refused(flat):
    old = api.start_tenancy(flat, IVANOV, "Иванов", date(2026, 1, 1), TERMS)
    api.end_tenancy(old, date(2026, 5, 31))

    with pytest.raises(api.AlreadyEnded):
        api.renew_tenancy(old, date(2026, 7, 1), TERMS)
