"""Разрыв cross-module FK на приборах и показаниях — шаги C2a и C2b.

Файл временный по замыслу: он пинает промежуточное состояние стандартной
процедуры (§0 плана миграции) и исчезнет, когда обе связи станут ссылкой по
идентификатору, а модели уедут в Metering.

Тесты фаз C2a1 (запись в оба поля) и C2a2 (переключение чтений) переписаны
шагом C2a3: проверять стало нечего — второго поля больше нет, а вместе с ним
нет и способа их разойтись. Осталось то, что шаг сделал уязвимым: защита
квартиры от удаления, которую держал `on_delete=PROTECT`.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.utils import timezone
from importlib import import_module

from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Meter, MeterReading, Tenant
from billing.services.statements import MissingBaselineError, _previous_readings

pytestmark = pytest.mark.django_db

READING_BACKFILL = import_module(
    "billing.migrations.0012_reading_gets_an_apartment_reference"
).fill_from_the_foreign_key

PERIOD = date(2026, 7, 1)


@pytest.fixture
def apartment():
    return Apartment.objects.create(label="кв. 1")


@pytest.fixture
def tenant_client(apartment):
    """Жилец, открывающий форму ввода показаний."""
    user = User.objects.create_user("zhilets", password="pass12345")
    Tenant.objects.create(user=user, apartment=apartment, full_name="Жилец",
                          privacy_consent_at=timezone.now(),
                          privacy_consent_version=PRIVACY_POLICY_VERSION)
    client = Client()
    client.login(username="zhilets", password="pass12345")
    return client


# ------------------------------------------------------ чтения по ссылке

def test_the_form_finds_meters_by_the_reference(tenant_client, apartment):
    """`views.py`: заводские номера в форме ввода показаний."""
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         serial_number="CW-77", initial_value=Decimal("0"))

    assert "CW-77" in tenant_client.get("/").content.decode()


def test_the_baseline_finds_meters_by_the_reference(apartment):
    """`statements.py`: начальные показания как база первого месяца."""
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         initial_value=Decimal("100"))

    assert _previous_readings(apartment, PERIOD, ["cold_water"]) == {
        "cold_water": Decimal("100")}


def test_one_apartment_does_not_see_another_apartments_meters(apartment):
    """Фильтр по ссылке — не украшение: без него база отсчёта одной квартиры
    собралась бы из приборов всех остальных."""
    neighbour = Apartment.objects.create(label="кв. 2")
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=neighbour.pk, kind="electricity_single",
                         initial_value=Decimal("777"))

    assert _previous_readings(apartment, PERIOD, ["cold_water"]) == {
        "cold_water": Decimal("100")}
    with pytest.raises(MissingBaselineError):
        _previous_readings(apartment, PERIOD, ["electricity_single"])


# ----------------------------------------- C2b1: ссылка у показания

def test_a_new_reading_gets_the_reference(apartment):
    reading = MeterReading.objects.create(
        apartment=apartment, period=PERIOD, meter="cold_water",
        value=Decimal("110"))

    assert MeterReading.objects.get(pk=reading.pk).apartment_ref == apartment.pk


def test_correcting_a_reading_keeps_the_reference(apartment):
    """Показание правится на месте (`obj.save()` в форме и в админке), и
    зеркалирование обязано пережить правку."""
    reading = MeterReading.objects.create(
        apartment=apartment, period=PERIOD, meter="cold_water",
        value=Decimal("110"))
    MeterReading.objects.filter(pk=reading.pk).update(apartment_ref=None)

    reading.value = Decimal("120")
    reading.save()

    assert MeterReading.objects.get(pk=reading.pk).apartment_ref == apartment.pk


def test_moving_a_reading_to_another_apartment_moves_the_reference(apartment):
    """Админка позволяет сменить квартиру у показания. Зеркалирование, которое
    заполняет поле только пустым, оставило бы показание числиться за прежней
    квартирой — и после C2b2 оно уехало бы в чужой счёт."""
    other = Apartment.objects.create(label="кв. 2")
    reading = MeterReading.objects.create(
        apartment=apartment, period=PERIOD, meter="cold_water",
        value=Decimal("110"))

    reading.apartment = other
    reading.save()

    assert MeterReading.objects.get(pk=reading.pk).apartment_ref == other.pk


def test_the_reading_backfill_copies_each_row_its_own_value():
    """`update(apartment_ref=F("apartment_id"))`, а не одно значение на всех:
    ошибка здесь приписала бы все показания одной квартире."""
    first = Apartment.objects.create(label="кв. 1")
    second = Apartment.objects.create(label="кв. 2")
    MeterReading.objects.create(apartment=first, period=PERIOD,
                                meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=second, period=PERIOD,
                                meter="cold_water", value=Decimal("220"))
    MeterReading.objects.update(apartment_ref=None)

    READING_BACKFILL(django_apps, None)

    assert set(MeterReading.objects.values_list("apartment_id", "apartment_ref")) == {
        (first.pk, first.pk), (second.pk, second.pk)}


def test_the_reading_backfill_fills_rows_written_before_the_step(apartment):
    reading = MeterReading.objects.create(
        apartment=apartment, period=PERIOD, meter="cold_water",
        value=Decimal("110"))
    MeterReading.objects.filter(pk=reading.pk).update(apartment_ref=None)

    READING_BACKFILL(django_apps, None)

    assert MeterReading.objects.get(pk=reading.pk).apartment_ref == apartment.pk


# ------------------------------------- защита взамен утраченного PROTECT

def test_an_apartment_with_a_meter_is_not_deleted(apartment):
    """Дефект №9 закрыт по-прежнему, хотя констрейнта, которым его закрыли,
    больше нет."""
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         initial_value=Decimal("100"))

    with pytest.raises(ProtectedError):
        apartment.delete()

    assert Apartment.objects.count() == 1
    assert Meter.objects.count() == 1


def test_bulk_delete_from_the_list_is_protected_too(apartment):
    """`queryset.delete()` — тот путь, которым удаляет админка, выделив
    квартиры галочками. Переопределения `Model.delete` он не касается, поэтому
    проверка продублирована в `delete()` менеджера."""
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         initial_value=Decimal("100"))

    with pytest.raises(ProtectedError):
        Apartment.objects.filter(pk=apartment.pk).delete()

    assert Apartment.objects.count() == 1


def test_the_refusal_names_what_holds_the_apartment(apartment):
    Meter.objects.create(apartment_id=apartment.pk, kind="cold_water",
                         initial_value=Decimal("100"))

    with pytest.raises(ProtectedError) as refusal:
        apartment.delete()

    assert "приборы учёта" in str(refusal.value)


def test_an_apartment_without_meters_still_deletes(apartment):
    """Защищается история, а не сама запись: опечатка в списке объектов
    остаётся исправимой."""
    apartment.delete()

    assert Apartment.objects.count() == 0


def test_a_neighbours_meter_does_not_hold_this_apartment(apartment):
    """Проверка обязана смотреть на приборы **этой** квартиры. Без фильтра
    любая заведённая где-либо строка запирала бы весь список объектов."""
    neighbour = Apartment.objects.create(label="кв. 2")
    Meter.objects.create(apartment_id=neighbour.pk, kind="cold_water",
                         initial_value=Decimal("100"))

    apartment.delete()

    assert set(Apartment.objects.values_list("pk", flat=True)) == {neighbour.pk}
