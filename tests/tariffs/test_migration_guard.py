"""Страж миграции `0003`: отказ вместо тихой чистки.

Шаг C1b вводит ограничения на таблицу, в которой их никогда не было, — значит
в базе владельца может лежать что угодно. Выбрать за него, какую из двух
версий оставить, нельзя: это разные цены, и разница уедет в счета жильцов.
Миграция обязана остановиться и перечислить, что разобрать руками.

**Почему тест выглядит так.** Проверить стража на данных, которые ограничения
уже не пускают, невозможно, поэтому ограничения на время снимаются прямо в
тесте. Это единственный способ увидеть стража за работой, не заводя вторую
базу: к моменту его вызова в настоящей миграции ограничений ещё нет.
"""

from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.db import connection

from modules.tariffs.infrastructure.models import TariffVersion

pytestmark = pytest.mark.django_db(transaction=True)

guard = import_module(
    "modules.tariffs.infrastructure.migrations.0003_versions_are_unique_and_positive"
).refuse_on_data_that_would_violate

JULY = date(2026, 7, 1)


@pytest.fixture
def table_without_constraints():
    """Снять ограничения, вернуть их обратно чего бы ни случилось.

    Снимаются с двух сторон сразу. SQLite не умеет удалять ограничение на
    месте: Django пересобирает таблицу целиком по объявлению модели, и пока
    ограничения перечислены в `_meta`, они переезжают в новую таблицу вместе
    со всем остальным. Настоящая миграция этой заботы не знает — она работает
    с исторической моделью, где ограничений ещё нет.
    """
    constraints = list(TariffVersion._meta.constraints)
    TariffVersion._meta.constraints = []
    with connection.schema_editor(atomic=False) as editor:
        for constraint in constraints:
            editor.remove_constraint(TariffVersion, constraint)
    try:
        yield
    finally:
        TariffVersion.objects.all().delete()
        TariffVersion._meta.constraints = constraints
        with connection.schema_editor(atomic=False) as editor:
            for constraint in constraints:
                editor.add_constraint(TariffVersion, constraint)


def _row(rate, effective_from=JULY, utility="cold_water"):
    TariffVersion.objects.create(utility=utility, rate=Decimal(rate),
                                 effective_from=effective_from)


def test_clean_table_passes(table_without_constraints):
    _row("48.15")
    _row("55.00", date(2026, 8, 1))

    guard(django_apps, None)          # молча, без исключения


def test_empty_table_passes(table_without_constraints):
    guard(django_apps, None)


def test_duplicates_stop_the_migration(table_without_constraints):
    _row("48.15")
    _row("55.00")

    with pytest.raises(RuntimeError):
        guard(django_apps, None)


def test_the_refusal_names_the_service_the_date_and_both_rates(table_without_constraints):
    """Перечень — весь смысл стража: без него владельцу нечего разбирать."""
    _row("48.15")
    _row("55.00")

    with pytest.raises(RuntimeError) as refusal:
        guard(django_apps, None)

    complaint = str(refusal.value)
    assert "cold_water" in complaint
    assert "2026-07-01" in complaint
    assert "48.1500" in complaint and "55.0000" in complaint


def test_non_positive_rates_stop_the_migration(table_without_constraints):
    _row("0")

    with pytest.raises(RuntimeError) as refusal:
        guard(django_apps, None)

    assert "cold_water" in str(refusal.value)


def test_negative_rate_stops_the_migration(table_without_constraints):
    _row("-10.00")

    with pytest.raises(RuntimeError):
        guard(django_apps, None)


def test_every_offender_is_listed_not_just_the_first(table_without_constraints):
    """Останавливаться на первой находке значило бы заставить владельца
    чинить по одной строке за прогон."""
    _row("48.15")
    _row("55.00")
    _row("0", date(2026, 8, 1))
    _row("-1", date(2026, 9, 1), utility="sewage")

    with pytest.raises(RuntimeError) as refusal:
        guard(django_apps, None)

    complaint = str(refusal.value)
    assert complaint.count("cold_water") == 2      # дубликат и нулевая ставка
    assert "sewage" in complaint


def test_the_refusal_explains_why_it_will_not_choose(table_without_constraints):
    _row("48.15")
    _row("55.00")

    with pytest.raises(RuntimeError) as refusal:
        guard(django_apps, None)

    assert "разные цены" in str(refusal.value)
