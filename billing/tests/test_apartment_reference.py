"""Разрыв cross-module FK на приборах и показаниях — шаги C2a и C2b.

Файл временный по замыслу: он пинает промежуточное состояние стандартной
процедуры (§0 плана миграции) и исчезнет, когда обе связи станут ссылкой по
идентификатору, а модели уедут в Metering.

Проверяется ровно то, что делает шаг опасным: строка без ссылки. Пока
читается FK, такая строка выглядит исправной, а после переключения чтений
пропадает из выборок — и обнаружится это не тестом, а пропавшим счётчиком у
жильца.
"""

from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from importlib import import_module

from billing.models import Apartment, Meter

pytestmark = pytest.mark.django_db

BACKFILL = import_module(
    "billing.migrations.0010_meter_gets_an_apartment_reference"
).fill_from_the_foreign_key


@pytest.fixture
def apartment():
    return Apartment.objects.create(label="кв. 1")


def test_a_new_meter_gets_the_reference(apartment):
    meter = Meter.objects.create(apartment=apartment, kind="cold_water",
                                 initial_value=Decimal("0"))

    assert meter.apartment_ref == apartment.pk


def test_the_reference_is_stored_not_just_set_in_memory(apartment):
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         initial_value=Decimal("0"))

    assert Meter.objects.get().apartment_ref == apartment.pk


def test_moving_a_meter_to_another_apartment_moves_the_reference(apartment):
    other = Apartment.objects.create(label="кв. 2")
    meter = Meter.objects.create(apartment=apartment, kind="cold_water",
                                 initial_value=Decimal("0"))

    meter.apartment = other
    meter.save()

    assert Meter.objects.get().apartment_ref == other.pk


def test_the_backfill_fills_rows_written_before_the_step(apartment):
    """Строки, заведённые до появления колонки. Воспроизводятся `update`,
    минуя `save`, — иначе зеркалирование их починит и проверять будет нечего."""
    meter = Meter.objects.create(apartment=apartment, kind="cold_water",
                                 initial_value=Decimal("0"))
    Meter.objects.filter(pk=meter.pk).update(apartment_ref=None)

    BACKFILL(django_apps, None)

    assert Meter.objects.get().apartment_ref == apartment.pk


def test_the_backfill_copies_each_row_its_own_value():
    """`update(apartment_ref=F("apartment_id"))`, а не одно значение на всех:
    ошибка здесь дала бы все приборы, приписанные одной квартире."""
    first = Apartment.objects.create(label="кв. 1")
    second = Apartment.objects.create(label="кв. 2")
    Meter.objects.create(apartment=first, kind="cold_water",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment=second, kind="cold_water",
                         initial_value=Decimal("0"))
    Meter.objects.update(apartment_ref=None)

    BACKFILL(django_apps, None)

    assert set(Meter.objects.values_list("apartment_id", "apartment_ref")) == {
        (first.pk, first.pk), (second.pk, second.pk)}


def test_reads_still_go_through_the_foreign_key(apartment):
    """Граница шага C2a1: ссылка заведена, но ничего на неё ещё не смотрит.
    Тест переписывается шагом C2a2 — тогда пропадёт и сам обход связи."""
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         initial_value=Decimal("0"))

    assert [m.kind for m in apartment.meters.all()] == ["cold_water"]
