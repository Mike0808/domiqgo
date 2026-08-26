"""Замок периода: закрытый месяц не принимает ни сдачи, ни правки.

`transaction=True`: снятие замка публикует событие, а оно доставляется после
фиксации.

Замок заведён на шаге C2g, но ставить его пока некому: команду `close_period`
зовёт Billing в момент выставления счёта, а такого момента у счёта ещё нет —
он появляется на **E4** ([ADR-0012](../../docs/architecture/adr/0012-metering-period-lock.md)).
Поэтому шаг ничего не меняет для пользователя: закрытых периодов в базе не
бывает, и инвариант, хотя и действует, ни на что не влияет. Проверяется он
здесь именно затем, чтобы к моменту E4 работал, а не начинал жизнь непроверенным.
"""

from datetime import date
from decimal import Decimal

import pytest

from bus import clear_subscribers, subscribe
from modules.metering import api
from modules.metering.events import MeteringPeriodReopened
from modules.metering.infrastructure.models import PeriodLock

pytestmark = pytest.mark.django_db(transaction=True)

JULY = date(2026, 7, 1)
AUGUST = date(2026, 8, 1)
APARTMENT = 1
NEIGHBOUR = 2


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def reopened():
    events = []
    subscribe(MeteringPeriodReopened, events.append)
    return events


# ----------------------------------------------------------- состояние замка

def test_a_period_is_open_until_it_is_closed():
    assert api.is_period_open(APARTMENT, JULY) is True


def test_closing_shuts_the_period():
    api.close_period(APARTMENT, JULY)

    assert api.is_period_open(APARTMENT, JULY) is False


def test_closing_one_period_leaves_the_next_open():
    api.close_period(APARTMENT, JULY)

    assert api.is_period_open(APARTMENT, AUGUST) is True


def test_closing_one_point_leaves_the_neighbour_open():
    """Замок принадлежит точке учёта, а не календарю: счёт выставляют по
    квартирам, а не всем сразу."""
    api.close_period(APARTMENT, JULY)

    assert api.is_period_open(NEIGHBOUR, JULY) is True


def test_closing_twice_is_not_an_error():
    """Команда описывает желаемое состояние, а не переход: второй счёт за тот
    же период не должен падать."""
    api.close_period(APARTMENT, JULY)
    api.close_period(APARTMENT, JULY)

    assert PeriodLock.objects.count() == 1


# ---------------------------------------------------------- закрытый период

def test_a_closed_period_refuses_a_submission():
    api.close_period(APARTMENT, JULY)

    with pytest.raises(api.PeriodClosed):
        api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})


def test_the_refusal_explains_itself_and_says_what_to_do():
    """Интерфейс обязан объяснить причину отказа — требование 2 ADR-0012."""
    api.close_period(APARTMENT, JULY)

    with pytest.raises(api.PeriodClosed) as refusal:
        api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    assert "07.2026" in str(refusal.value)
    assert "снимите замок" in str(refusal.value).lower()


def test_a_refused_submission_stores_nothing():
    api.close_period(APARTMENT, JULY)

    with pytest.raises(api.PeriodClosed):
        api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    assert api.get_readings(APARTMENT, JULY) == {}


def test_a_closed_period_refuses_a_correction():
    """Инвариант охватывает и правку: иначе замок обходился бы через админку —
    ровно так, как сегодняшняя блокировка в представлении обходится ею."""
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    api.close_period(APARTMENT, JULY)

    with pytest.raises(api.PeriodClosed):
        api.correct_reading(APARTMENT, JULY, "cold_water", Decimal("115"))

    assert api.get_readings(APARTMENT, JULY) == {"cold_water": Decimal("110.000")}


def test_an_open_period_of_the_same_point_still_accepts():
    api.close_period(APARTMENT, JULY)

    api.submit_readings(APARTMENT, AUGUST, {"cold_water": Decimal("120")})

    assert api.get_readings(APARTMENT, AUGUST) == {"cold_water": Decimal("120.000")}


def test_a_neighbours_lock_does_not_block_this_point():
    api.close_period(NEIGHBOUR, JULY)

    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})

    assert api.get_readings(APARTMENT, JULY) == {"cold_water": Decimal("110.000")}


# --------------------------------------------------------------- снятие замка

def test_reopening_lets_the_readings_in_again(reopened):
    """Без этого первая же опечатка в показаниях превращалась бы в тупик —
    требование 3 ADR-0012."""
    api.close_period(APARTMENT, JULY)

    api.reopen_period(APARTMENT, JULY)

    assert api.is_period_open(APARTMENT, JULY) is True
    api.submit_readings(APARTMENT, JULY, {"cold_water": Decimal("110")})
    assert api.get_readings(APARTMENT, JULY) == {"cold_water": Decimal("110.000")}


def test_reopening_announces_itself(reopened):
    """Ручное вмешательство в закрытый месяц оставляет след независимо от
    того, слушает ли его сегодня кто-нибудь."""
    api.close_period(APARTMENT, JULY)

    api.reopen_period(APARTMENT, JULY)

    assert [(e.apartment_id, e.period) for e in reopened] == [(APARTMENT, JULY)]


def test_closing_announces_nothing(reopened):
    """Закрытие инициировал сам Billing — сообщать ему о последствии
    собственного решения незачем."""
    from bus.models import PublishedEvent

    api.close_period(APARTMENT, JULY)

    assert PublishedEvent.objects.count() == 0


def test_reopening_a_period_that_was_never_closed_announces_nothing(reopened):
    api.reopen_period(APARTMENT, JULY)

    assert reopened == []


def test_reopening_one_period_leaves_the_other_closed():
    """Снимается замок названного месяца, а не все замки точки учёта.

    Соседняя квартира этого не ловит: у неё своя строка, и запрос без фильтра
    по периоду всё равно её не тронет. Разница видна только на двух закрытых
    месяцах одной квартиры — а это и есть обычное положение дел к концу года.
    """
    api.close_period(APARTMENT, JULY)
    api.close_period(APARTMENT, AUGUST)

    api.reopen_period(APARTMENT, JULY)

    assert api.is_period_open(APARTMENT, JULY) is True
    assert api.is_period_open(APARTMENT, AUGUST) is False


def test_reopening_leaves_the_neighbour_locked():
    api.close_period(APARTMENT, JULY)
    api.close_period(NEIGHBOUR, JULY)

    api.reopen_period(APARTMENT, JULY)

    assert api.is_period_open(NEIGHBOUR, JULY) is False
