"""Разрыв cross-module FK на приборах и показаниях — шаги C2a и C2b.

Файл временный по замыслу: он пинает промежуточное состояние стандартной
процедуры (§0 плана миграции) и исчезнет, когда обе связи станут ссылкой по
идентификатору, а модели уедут в Metering.

Проверяется ровно то, что делает шаг опасным: строка без ссылки. Пока
читается FK, такая строка выглядит исправной, а после переключения чтений
пропадает из выборок — и обнаружится это не тестом, а пропавшим счётчиком у
жильца.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.utils import timezone
from importlib import import_module

from billing.consent import PRIVACY_POLICY_VERSION

from billing.models import Apartment, Meter, Tenant
from billing.services.statements import (
    MissingBaselineError, _previous_readings,
)

pytestmark = pytest.mark.django_db

BACKFILL = import_module(
    "billing.migrations.0010_meter_gets_an_apartment_reference"
).fill_from_the_foreign_key


PERIOD = date(2026, 7, 1)


@pytest.fixture
def apartment():
    return Apartment.objects.create(label="кв. 1")


@pytest.fixture
def tenant_client(apartment):
    """Жилец, открывающий форму ввода показаний."""
    from django.contrib.auth.models import User
    from django.test import Client

    user = User.objects.create_user("zhilets", password="pass12345")
    Tenant.objects.create(user=user, apartment=apartment, full_name="Жилец",
                          privacy_consent_at=timezone.now(),
                          privacy_consent_version=PRIVACY_POLICY_VERSION)
    client = Client()
    client.login(username="zhilets", password="pass12345")
    return client


def _elsewhere():
    """Другая квартира — чтобы обход связи, если он остался, дал другой ответ."""
    return Apartment.objects.create(label="не та квартира")


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


# --------------------------------------------------- C2a2: чтения по ссылке

def test_the_form_finds_meters_by_the_reference(tenant_client, apartment):
    """`views.py`: заводские номера в форме ввода показаний."""
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         serial_number="CW-77", initial_value=Decimal("0"))
    Meter.objects.filter(kind="cold_water").update(apartment=_elsewhere())

    assert "CW-77" in tenant_client.get("/").content.decode()


def test_the_baseline_finds_meters_by_the_reference(apartment):
    """`statements.py`: начальные показания как база первого месяца."""
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         initial_value=Decimal("100"))
    Meter.objects.filter(kind="cold_water").update(apartment=_elsewhere())

    assert _previous_readings(apartment, PERIOD, ["cold_water"]) == {
        "cold_water": Decimal("100")}


def test_one_apartment_does_not_see_another_apartments_meters(apartment):
    """Фильтр по ссылке — не украшение: без него база отсчёта одной квартиры
    собралась бы из приборов всех остальных."""
    neighbour = Apartment.objects.create(label="кв. 2")
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         initial_value=Decimal("100"))
    Meter.objects.create(apartment=neighbour, kind="electricity_single",
                         initial_value=Decimal("777"))

    assert _previous_readings(apartment, PERIOD, ["cold_water"]) == {
        "cold_water": Decimal("100")}
    with pytest.raises(MissingBaselineError):
        _previous_readings(apartment, PERIOD, ["electricity_single"])


def test_a_meter_left_without_a_reference_stops_the_calculation(apartment):
    """Цена шага, названная вслух — и она оказалась приемлемой.

    Пока читался FK, строка без ссылки выглядела исправной; теперь она
    невидима. Но невидимый прибор не превращается в счёт от неявного нуля:
    исчезает и база отсчёта, а расчёт без базы отказывается считать
    (`MissingBaselineError`, введён до этого плана). То есть худший исход
    шага — остановка с сообщением, а не завышенный счёт жильцу.
    """
    Meter.objects.create(apartment=apartment, kind="cold_water",
                         initial_value=Decimal("100"))
    Meter.objects.update(apartment_ref=None)

    with pytest.raises(MissingBaselineError):
        _previous_readings(apartment, PERIOD, ["cold_water"])
