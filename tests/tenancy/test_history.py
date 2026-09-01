"""Договор и история заселений — правила без базы.

Ни одного `django_db`: инварианты обязаны проверяться без хранилища.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from modules.tenancy.domain import (
    AlreadyEnded, EndBeforeStart, PeriodOverlap, PropertyHistory,
    PropertyOutOfService, Tenancy, Terms,
)

TERMS = Terms(rent=Decimal("30000"), internet=Decimal("500"))


def _tenancy(started, ended=None, tenancy_id=None, account_id=1):
    return Tenancy(tenancy_id=tenancy_id, property_id=7, account_id=account_id,
                   full_name="Иванов", started_on=started, ended_on=ended, terms=TERMS)


# ------------------------------------------------------------- инвариант 2

def test_moving_out_before_moving_in_is_impossible():
    with pytest.raises(EndBeforeStart):
        _tenancy(date(2026, 3, 1), ended=date(2026, 2, 28))


def test_moving_out_on_the_move_in_day_is_a_one_day_tenancy():
    t = _tenancy(date(2026, 3, 1), ended=date(2026, 3, 1))
    assert t.covers(date(2026, 3, 1)) and not t.covers(date(2026, 3, 2))


def test_an_ended_tenancy_cannot_end_again():
    with pytest.raises(AlreadyEnded):
        _tenancy(date(2026, 3, 1), ended=date(2026, 6, 30)).end(date(2026, 7, 31))


def test_a_tenancy_without_move_out_is_open_and_covers_the_far_future():
    t = _tenancy(date(2026, 3, 1))
    assert t.is_open and t.covers(date(2099, 1, 1))


# ------------------------------------------------------------- инвариант 1

def test_a_property_never_has_two_tenancies_on_one_day():
    history = PropertyHistory(7, [_tenancy(date(2026, 1, 1), ended=date(2026, 6, 30), tenancy_id=1)])
    with pytest.raises(PeriodOverlap):
        history.start(_tenancy(date(2026, 6, 30), account_id=2))


def test_the_next_tenancy_may_start_the_day_after_the_previous_ends():
    history = PropertyHistory(7, [_tenancy(date(2026, 1, 1), ended=date(2026, 6, 30), tenancy_id=1)])
    history.start(_tenancy(date(2026, 7, 1), account_id=2))
    assert len(history.tenancies) == 2


def test_an_open_tenancy_blocks_every_later_start():
    history = PropertyHistory(7, [_tenancy(date(2026, 1, 1), tenancy_id=1)])
    with pytest.raises(PeriodOverlap):
        history.start(_tenancy(date(2030, 1, 1), account_id=2))


def test_overlaps_left_by_the_migration_do_not_break_reading_the_history():
    """До D3 у квартиры может быть несколько черновиков на одни даты. Читать
    историю можно; добавить ещё один договор — нельзя."""
    history = PropertyHistory(7, [_tenancy(date(2026, 1, 1), tenancy_id=1),
                                  _tenancy(date(2026, 1, 1), tenancy_id=2, account_id=2)])
    assert history.active_on(date(2026, 5, 1)).tenancy_id == 1
    with pytest.raises(PeriodOverlap):
        history.start(_tenancy(date(2027, 1, 1), account_id=3))


# ------------------------------------------------------------- инвариант 5

def test_a_decommissioned_property_takes_no_new_tenancy():
    history = PropertyHistory(7, out_of_service=True)
    with pytest.raises(PropertyOutOfService):
        history.start(_tenancy(date(2026, 1, 1)))


def test_decommissioning_does_not_end_the_running_tenancy():
    """ADR-0009: дата выезда — факт, а не следствие отметки."""
    running = _tenancy(date(2026, 1, 1), tenancy_id=1)
    history = PropertyHistory(7, [running], out_of_service=True)
    assert history.active_on(date(2026, 9, 1)) is running


# -------------------------------------------------------------- ADR-0024

def test_the_tenancy_of_record_is_the_one_active_on_the_first_day_of_the_period():
    """Переезд пятого числа означает, что весь месяц считается на прежнего
    жильца. Пропорциональное деление — P2."""
    old = _tenancy(date(2026, 1, 1), ended=date(2026, 3, 5), tenancy_id=1)
    new = _tenancy(date(2026, 3, 6), tenancy_id=2, account_id=2)
    history = PropertyHistory(7, [old, new])

    assert history.of_record_for(date(2026, 3, 1)) is old
    assert history.of_record_for(date(2026, 4, 1)) is new


def test_an_empty_property_has_no_tenancy_of_record():
    old = _tenancy(date(2026, 1, 1), ended=date(2026, 2, 28), tenancy_id=1)
    assert PropertyHistory(7, [old]).of_record_for(date(2026, 3, 1)) is None


# ------------------------------------------------------------- инвариант 3

def test_terms_are_immutable():
    with pytest.raises(FrozenInstanceError):
        TERMS.rent = Decimal("1")
