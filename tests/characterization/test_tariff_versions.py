"""Тарифная линия: пункт №28 гап-анализа.

| Пункт | Что зафиксировано                                        | Кто перепишет |
|-------|----------------------------------------------------------|---------------|
| №28   | две версии на одну услугу и дату уживаются молча          | C1b           |
| №28   | ставка может быть нулевой и отрицательной                 | C1b           |

Пункт не помечен ⚠ и в каталог шага A3 не попал: он классифицирован как
**БД** — «требует изменения схемы», а критерием отбора было «меняется
поведение». Отбор оказался узок. Ограничение появляется не в вакууме: команда,
которая сегодня молча заводит вторую версию, начнёт отказывать, и владелец
это увидит. Тест заведён перед шагом C1b, чтобы изменение было видно в диффе
как правка теста, а не как его отсутствие.

Шаг C1a переносом ничего здесь не изменил — и это тоже зафиксировано: ниже
проверяется поведение, доставшееся от `billing.Tariff` без правок.

**Отдельно о недетерминированности.** Через базу выбор версии из двух с
одинаковой датой не определён ничем: строки читаются без `ORDER BY`, а
сортировка линии по дате устойчива и порядок равных сохраняет. Поэтому тест
не утверждает, *какая* из двух выиграет — он утверждает, что выигрывает одна
из них и модуль на этот счёт ничего не обещает. Утверждать большее значило бы
закрепить случайность как правило.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.tariffs import api
from modules.tariffs.infrastructure.models import TariffVersion

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]

JULY = date(2026, 7, 1)


def test_second_version_on_the_same_date_is_accepted_silently():
    """Сегодня это не ошибка и даже не предупреждение."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)

    assert TariffVersion.objects.filter(utility="cold_water").count() == 2
    assert len(api.list_versions("cold_water")) == 2


def test_which_of_two_versions_applies_is_not_promised():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)

    applied = api.get_rate_on("cold_water", JULY).rate

    assert applied in (Decimal("48.15"), Decimal("55.00"))


def test_duplicate_reaches_the_bill_as_a_silent_choice():
    """Счёт посчитается по одной из двух ставок, и в нём не будет ни следа
    того, что была вторая."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)

    rates = api.get_rates_on(JULY)

    assert set(rates) == {"cold_water"}          # не две строки, а одна
    assert rates["cold_water"].rate in (Decimal("48.15"), Decimal("55.00"))


def test_zero_rate_is_accepted():
    """Нулевая ставка даёт строку счёта на 0 ₽ — ровно тот сорт молчаливого
    дефекта, что и норматив подогрева ГВС (№29)."""
    api.publish_tariff_version("cold_water", Decimal("0"), JULY)

    assert api.get_rate_on("cold_water", JULY).rate == Decimal("0")


def test_negative_rate_is_accepted():
    """Отрицательная ставка уменьшает счёт. Ошибкой сегодня не считается."""
    api.publish_tariff_version("cold_water", Decimal("-10.00"), JULY)

    assert api.get_rate_on("cold_water", JULY).rate == Decimal("-10.00")
