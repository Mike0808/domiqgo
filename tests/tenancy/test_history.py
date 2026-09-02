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


def test_drafts_do_not_block_and_do_not_beat_a_confirmed_tenancy():
    """Черновики миграции — предложения, а не факты (D3): пересекаются между
    собой, не мешают заселению и проигрывают подтверждённому договору."""
    drafts = [Tenancy(tenancy_id=1, property_id=7, account_id=1, full_name="И",
                      started_on=date(2026, 1, 1), terms=TERMS, start_confirmed=False),
              Tenancy(tenancy_id=2, property_id=7, account_id=2, full_name="А",
                      started_on=date(2026, 1, 1), terms=TERMS, start_confirmed=False)]
    history = PropertyHistory(7, drafts)
    assert history.active_on(date(2026, 5, 1)).tenancy_id == 1   # ранний из черновиков

    confirmed = history.start(_tenancy(date(2026, 3, 1), account_id=3, tenancy_id=3))

    assert history.active_on(date(2026, 5, 1)) is confirmed      # подтверждённый побеждает
    with pytest.raises(PeriodOverlap):                           # а сам занимает период
        history.start(_tenancy(date(2027, 1, 1), account_id=4))


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


# --------------------------------------------- исправление сведений (D2)

def test_correcting_the_date_confirms_it():
    draft = Tenancy(tenancy_id=1, property_id=7, account_id=1, full_name="Иванов",
                    started_on=date(2026, 9, 1), terms=TERMS, start_confirmed=False)

    corrected, changes = draft.correct(started_on=date(2026, 3, 1))

    assert corrected.start_confirmed is True
    assert changes == ("started_on: 2026-09-01 -> 2026-03-01",)


def test_confirming_the_proposed_date_changes_nothing_but_the_mark():
    draft = Tenancy(tenancy_id=1, property_id=7, account_id=1, full_name="Иванов",
                    started_on=date(2026, 9, 1), terms=TERMS, start_confirmed=False)

    corrected, changes = draft.correct(started_on=date(2026, 9, 1))

    assert corrected.start_confirmed is True and changes == ()


def test_correcting_terms_names_each_changed_amount():
    t = _tenancy(date(2026, 3, 1), tenancy_id=1)

    _, changes = t.correct(terms=Terms(rent=Decimal("35000"), internet=Decimal("500")))

    assert changes == ("rent: 30000 -> 35000",)


def test_a_correction_may_not_land_on_a_confirmed_neighbour():
    """Подтверждённый договор занимает период по-настоящему."""
    confirmed = _tenancy(date(2026, 1, 1), ended=date(2026, 6, 30), tenancy_id=1)
    draft = Tenancy(tenancy_id=2, property_id=7, account_id=2, full_name="Иванова",
                    started_on=date(2026, 7, 1), terms=TERMS, start_confirmed=False)
    history = PropertyHistory(7, [confirmed, draft])

    with pytest.raises(PeriodOverlap):
        history.correct(draft.correct(started_on=date(2026, 5, 1))[0])


def test_a_correction_ignores_unconfirmed_drafts():
    """Черновики миграции не запирают диалог подтверждения."""
    other_draft = Tenancy(tenancy_id=1, property_id=7, account_id=1, full_name="Иванов",
                          started_on=date(2026, 9, 1), terms=TERMS, start_confirmed=False)
    draft = Tenancy(tenancy_id=2, property_id=7, account_id=2, full_name="Иванова",
                    started_on=date(2026, 9, 1), terms=TERMS, start_confirmed=False)
    history = PropertyHistory(7, [other_draft, draft])

    corrected = history.correct(draft.correct(started_on=date(2026, 9, 1))[0])

    assert corrected.start_confirmed is True
