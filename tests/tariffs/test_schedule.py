"""Тарифная линия — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища, и этот файл —
доказательство, что он таким и получился. Появление здесь фикстуры `db` будет
означать, что правило утекло в инфраструктуру.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.tariffs.domain import (
    TariffSchedule, UnknownUtility, VersionNotFound,
)

JULY = date(2026, 7, 1)
JANUARY = date(2026, 1, 1)


def _line(*versions):
    """Линия ХВС из пар (ставка, дата)."""
    schedule = TariffSchedule("cold_water")
    for rate, effective_from in versions:
        schedule.publish(Decimal(rate), effective_from)
    return schedule


# ------------------------------------------------------------------- каталог

def test_unknown_utility_is_refused():
    """Каталог услуг — словарь Tariffs, и линию вне его завести нельзя."""
    with pytest.raises(UnknownUtility):
        TariffSchedule("hot_water")   # вид прибора Metering, а не услуга


def test_meter_kinds_are_not_utilities():
    """`hot_water` измеряется одним прибором, но тарифицируется двумя
    услугами — ADR-0003, три независимых словаря."""
    line = TariffSchedule("hot_water_cold_component")
    assert line.utility == "hot_water_cold_component"


# --------------------------------------------------------- ставка на дату

def test_rate_on_picks_the_latest_version_not_exceeding_the_date():
    line = _line(("40.00", date(2025, 7, 1)), ("48.15", JULY))

    assert line.rate_on(date(2026, 6, 30)).rate == Decimal("40.00")
    assert line.rate_on(JULY).rate == Decimal("48.15")
    assert line.rate_on(date(2027, 1, 1)).rate == Decimal("48.15")


def test_version_applies_from_its_first_day_inclusive():
    line = _line(("48.15", JULY))

    assert line.rate_on(date(2026, 6, 30)) is None
    assert line.rate_on(JULY) is not None


def test_no_rate_before_the_first_version_is_not_an_error():
    """«Ставки нет» — нормальный результат. Ошибкой его назначает Billing."""
    assert _line(("48.15", JULY)).rate_on(JANUARY) is None
    assert TariffSchedule("cold_water").rate_on(JULY) is None


def test_future_version_does_not_affect_today():
    """Ставку с 1 июля владелец заводит в июне, и июнь она не трогает."""
    line = _line(("40.00", JANUARY), ("48.15", JULY))

    assert line.rate_on(date(2026, 6, 15)).rate == Decimal("40.00")


def test_insertion_order_does_not_matter():
    """Порядок ввода — не порядок действия. В as-is выбор версии зависел от
    `Meta.ordering`, то есть от способа хранения."""
    late_first = _line(("48.15", JULY), ("40.00", JANUARY))
    early_first = _line(("40.00", JANUARY), ("48.15", JULY))

    assert late_first.rate_on(date(2026, 3, 1)).rate == Decimal("40.00")
    assert early_first.rate_on(date(2026, 3, 1)).rate == Decimal("40.00")


# ------------------------------------------------------------------ отрезок

def test_effective_range_ends_where_the_next_version_starts():
    """Отрезок нужен `TariffVersionCorrected`: подписчик обязан найти
    затронутые счета, не обращаясь обратно в Tariffs (ADR-0005)."""
    line = _line(("40.00", JANUARY), ("48.15", JULY))

    assert line.effective_range(JANUARY) == (JANUARY, JULY)


def test_last_version_has_an_open_ended_range():
    line = _line(("40.00", JANUARY), ("48.15", JULY))

    assert line.effective_range(JULY) == (JULY, None)


def test_range_of_a_version_that_is_not_there():
    with pytest.raises(VersionNotFound):
        _line(("48.15", JULY)).effective_range(JANUARY)


# ------------------------------------------------------------------ команды

def test_correct_replaces_the_version_and_reports_both_sides():
    line = _line(("4.85", JULY))

    previous, corrected = line.correct(JULY, rate=Decimal("48.15"))

    assert previous.rate == Decimal("4.85")     # опечатка: пропущенный ноль
    assert corrected.rate == Decimal("48.15")
    assert len(line.versions) == 1


def test_correct_can_move_the_date():
    """Версию опознаёт дата, с которой она действует **сейчас**; править её же
    иначе было бы невозможно выразить."""
    line = _line(("48.15", date(2026, 7, 11)))

    line.correct(date(2026, 7, 11), effective_from=JULY)

    assert [v.effective_from for v in line.versions] == [JULY]


def test_correct_leaves_untouched_fields_alone():
    line = TariffSchedule("cold_water")
    line.publish(Decimal("48.15"), JULY, "Постановление 123", "https://example/1")

    _, corrected = line.correct(JULY, rate=Decimal("48.20"))

    assert corrected.source_name == "Постановление 123"
    assert corrected.source_url == "https://example/1"


def test_correcting_a_version_that_is_not_there():
    with pytest.raises(VersionNotFound):
        _line(("48.15", JULY)).correct(JANUARY, rate=Decimal("1"))


def test_withdraw_removes_the_version():
    line = _line(("40.00", JANUARY), ("48.15", JULY))

    withdrawn = line.withdraw(JULY)

    assert withdrawn.rate == Decimal("48.15")
    assert [v.effective_from for v in line.versions] == [JANUARY]
    assert line.rate_on(JULY).rate == Decimal("40.00")   # действует прежняя


def test_line_may_end_up_with_no_versions():
    """Услуга без ставки — законное состояние, а не поломка."""
    line = _line(("48.15", JULY))

    line.withdraw(JULY)

    assert line.versions == []
    assert line.rate_on(JULY) is None


def test_withdrawing_a_version_that_is_not_there():
    with pytest.raises(VersionNotFound):
        _line(("48.15", JULY)).withdraw(JANUARY)


def test_versions_are_immutable():
    """Изменение цены порождает новую версию, а не правит старую."""
    version = _line(("48.15", JULY)).versions[0]

    with pytest.raises(Exception):
        version.rate = Decimal("50.00")


def test_versions_property_does_not_expose_the_internal_list():
    line = _line(("48.15", JULY))

    line.versions.clear()

    assert len(line.versions) == 1
