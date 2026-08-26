"""Точка учёта — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища, и этот файл —
доказательство, что он таким и получился. Появление здесь фикстуры `db` будет
означать, что правило утекло в инфраструктуру.

База отсчёта и монотонность приехали шагом C2d из `billing/services/`:
первая — из `statements._previous_readings`, вторая — из
`calculation._consumption`, то есть из середины расчёта счёта. Тест на
монотонность переехал сюда из `billing/tests/test_calculation.py` тем же шагом.
Замок периода добавлен на C2g — его в `billing/` не было вовсе: сегодняшняя
блокировка ввода живёт в представлении и читает статус счёта.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.metering.domain import (
    BaselineMissing, MeteringPoint, PeriodClosed, ReadingWentBackwards,
    ensure_period_open,
)


def _point(initial=None, previous=None, current=None):
    return MeteringPoint(apartment_id=1, initial_values=initial or {},
                         previous_values=previous or {},
                         current_values=current or {})


# ------------------------------------------------------------- база отсчёта

def test_baseline_is_the_previous_periods_reading():
    point = _point(initial={"cold_water": Decimal("50")},
                   previous={"cold_water": Decimal("100")})

    assert point.baseline_for("cold_water") == Decimal("100")


def test_baseline_falls_back_to_the_meters_initial_value():
    """Первый месяц: показаний ещё не сдавали, но акт при подписании договора
    зафиксировал, с чего прибор начинал."""
    point = _point(initial={"cold_water": Decimal("50")})

    assert point.baseline_for("cold_water") == Decimal("50")


def test_last_months_reading_beats_the_act():
    """Порядок не случаен: показание за прошлый месяц точнее акта двухлетней
    давности."""
    point = _point(initial={"cold_water": Decimal("50")},
                   previous={"cold_water": Decimal("100")})

    assert point.baseline_for("cold_water") == Decimal("100")


def test_no_baseline_at_all():
    assert _point().baseline_for("cold_water") is None


def test_a_zero_initial_value_is_a_baseline_not_an_absence():
    """`0` — законная база: новый прибор так и начинает. Проверка на «пусто»
    обязана отличать ноль от отсутствия, иначе первый месяц нового счётчика
    отказался бы считаться."""
    point = _point(initial={"cold_water": Decimal("0")})

    assert point.baseline_for("cold_water") == Decimal("0")


# ------------------------------------------------------------------- расход

def test_consumption_is_the_difference():
    point = _point(previous={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("110")})

    used = point.consumption(["cold_water"])["cold_water"]

    assert used.used == Decimal("10")
    assert (used.baseline, used.current) == (Decimal("100"), Decimal("110"))


def test_consumption_reports_both_ends_of_the_interval():
    """Границы едут наружу не для красоты: счёт обязан их напечатать — жилец
    должен видеть, из чего получилась цифра."""
    point = _point(initial={"cold_water": Decimal("50")},
                   current={"cold_water": Decimal("70")})

    used = point.consumption(["cold_water"])["cold_water"]

    assert (used.baseline, used.current, used.used) == (
        Decimal("50"), Decimal("70"), Decimal("20"))


def test_zero_consumption_is_legitimate():
    """Квартира могла стоять пустой. Ноль — не ошибка."""
    point = _point(previous={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("100")})

    assert point.consumption(["cold_water"])["cold_water"].used == Decimal("0")


def test_consumption_is_computed_per_resource():
    point = _point(previous={"cold_water": Decimal("100"),
                             "electricity_single": Decimal("1400")},
                   current={"cold_water": Decimal("110"),
                            "electricity_single": Decimal("1500")})

    used = point.consumption(["cold_water", "electricity_single"])

    assert {r: c.used for r, c in used.items()} == {
        "cold_water": Decimal("10"), "electricity_single": Decimal("100")}


def test_only_the_requested_resources_are_answered():
    """Что начислять этой квартире, решает Billing: Metering отвечает ровно на
    заданный вопрос и своего списка не навязывает."""
    point = _point(previous={"cold_water": Decimal("100"),
                             "hot_water": Decimal("50")},
                   current={"cold_water": Decimal("110"),
                            "hot_water": Decimal("55")})

    assert list(point.consumption(["cold_water"])) == ["cold_water"]


# --------------------------------------------------------------- отказы

def test_a_reading_below_the_baseline_is_refused():
    """Счётчик не отматывается назад: значение меньше прежнего — либо
    опечатка, либо замена прибора, и истолковать это за владельца нельзя."""
    point = _point(previous={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("90")})

    with pytest.raises(ReadingWentBackwards):
        point.consumption(["cold_water"])


def test_the_refusal_names_the_resource_and_both_values():
    point = _point(previous={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("90")})

    with pytest.raises(ReadingWentBackwards) as refusal:
        point.consumption(["cold_water"])

    assert "cold_water" in str(refusal.value)
    assert "100" in str(refusal.value) and "90" in str(refusal.value)


def test_a_reading_below_the_initial_value_is_refused_too():
    """Правило одно и то же независимо от того, откуда взялась база."""
    point = _point(initial={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("90")})

    with pytest.raises(ReadingWentBackwards):
        point.consumption(["cold_water"])


def test_a_resource_without_a_baseline_is_refused():
    """Считать от неявного нуля нельзя: расход вышел бы равным всему
    показанию прибора, и жилец заплатил бы за годы до себя."""
    point = _point(current={"cold_water": Decimal("110")})

    with pytest.raises(BaselineMissing):
        point.consumption(["cold_water"])


def test_the_refusal_names_every_resource_without_a_baseline():
    """Отсутствие базы — беда всей точки: сообщать о ней надо целиком, а не по
    одному ресурсу за прогон, иначе владелец чинит по кругу."""
    point = _point(initial={"cold_water": Decimal("0")},
                   current={"cold_water": Decimal("110"),
                            "hot_water": Decimal("55"),
                            "electricity_single": Decimal("1500")})

    with pytest.raises(BaselineMissing) as refusal:
        point.consumption(["cold_water", "hot_water", "electricity_single"])

    assert refusal.value.resources == ["hot_water", "electricity_single"]


def test_a_missing_baseline_is_reported_before_a_backward_reading():
    """Порядок отказов сохранён с точностью до сообщения: до шага C2d база
    отсчёта проверялась целиком раньше, чем считался расход, и владелец видел
    именно это сообщение."""
    point = _point(previous={"cold_water": Decimal("100")},
                   current={"cold_water": Decimal("90"),
                            "hot_water": Decimal("55")})

    with pytest.raises(BaselineMissing):
        point.consumption(["cold_water", "hot_water"])


# -------------------------------------------------------- замок периода

def test_an_open_period_passes():
    ensure_period_open(date(2026, 7, 1), set())


def test_a_closed_period_is_refused():
    with pytest.raises(PeriodClosed):
        ensure_period_open(date(2026, 7, 1), {date(2026, 7, 1)})


def test_only_the_named_period_is_closed():
    """Замок ставится на период, а не на точку учёта целиком: закрытый июль не
    должен запирать август."""
    ensure_period_open(date(2026, 8, 1), {date(2026, 7, 1)})


def test_the_refusal_names_the_period_and_the_way_out():
    with pytest.raises(PeriodClosed) as refusal:
        ensure_period_open(date(2026, 7, 1), {date(2026, 7, 1)})

    assert "07.2026" in str(refusal.value)
    assert "снимите замок" in str(refusal.value).lower()
