"""Что осталось у `billing/` от приборов и показаний — шаги C2a…C2d.

Связи разорваны, модели уехали в Metering, правила учёта — следом. Здесь
проверяется только то, что осталось задачей `billing/`:

- защита квартиры от удаления, которую держал `on_delete=PROTECT`, а теперь
  держит явная проверка через публичный API модуля;
- форма ввода показаний, которую собирает представление.

Изоляция точек учёта, база отсчёта и монотонность проверяются в
`tests/metering/`: правила там, где живут. Файл временный и исчезнет на C3,
когда удаление квартиры заменится выводом из эксплуатации.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.utils import timezone

from modules.metering.infrastructure.models import Meter, MeterReading
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Tenant


pytestmark = pytest.mark.django_db

PERIOD = date(2026, 7, 1)


def freeze_period():
    """Портал показывает текущий месяц; тесты живут в июле 2026."""
    return patch("billing.views._current_period", return_value=PERIOD)


@pytest.fixture
def apartment():
    """Простейшая квартира: холодная вода и однотарифный свет.

    Без горячей воды и водоотведения — тогда расчёт при сдаче показаний
    требует двух тарифов, а не пяти, и тесты этого файла остаются про ссылку,
    а не про начисление.
    """
    return Apartment.objects.create(label="кв. 1", has_hot_water=False,
                                    has_sewage=False)


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


# ------------------------------------------------- форма ввода показаний

def test_the_form_shows_serial_numbers_from_metering(tenant_client, apartment):
    """`views.py` строит форму из реестра приборов модуля."""
    Meter.objects.create(apartment_id=apartment.pk, resource="cold_water",
                         serial_number="CW-77", initial_value=Decimal("0"))

    assert "CW-77" in tenant_client.get("/").content.decode()


def test_the_form_prefills_readings_from_metering(tenant_client, apartment):
    Meter.objects.create(apartment_id=apartment.pk, resource="cold_water",
                         initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=apartment.pk, period=PERIOD,
                                resource="cold_water", value=Decimal("123.456"))

    with freeze_period():
        page = tenant_client.get("/").content.decode()

    assert "123.456" in page


# -------------------------------------- защита взамен утраченного PROTECT

def test_an_apartment_with_a_meter_is_not_deleted(apartment):
    """Дефект №9 закрыт по-прежнему, хотя констрейнта, которым его закрыли,
    больше нет."""
    Meter.objects.create(apartment_id=apartment.pk, resource="cold_water",
                         initial_value=Decimal("100"))

    with pytest.raises(ProtectedError):
        apartment.delete()

    assert Apartment.objects.count() == 1
    assert Meter.objects.count() == 1


def test_an_apartment_with_readings_is_not_deleted(apartment):
    """Показания держат квартиру сами, без приборов: строка истории есть, и
    удалять её вместе с квартирой молча нельзя."""
    MeterReading.objects.create(apartment_id=apartment.pk, period=PERIOD,
                                resource="cold_water", value=Decimal("110"))

    with pytest.raises(ProtectedError):
        apartment.delete()

    assert MeterReading.objects.count() == 1


def test_bulk_delete_from_the_list_is_protected_too(apartment):
    """`queryset.delete()` — тот путь, которым удаляет админка, выделив
    квартиры галочками. Переопределения `Model.delete` он не касается, поэтому
    проверка продублирована в `delete()` менеджера."""
    Meter.objects.create(apartment_id=apartment.pk, resource="cold_water",
                         initial_value=Decimal("100"))

    with pytest.raises(ProtectedError):
        Apartment.objects.filter(pk=apartment.pk).delete()

    assert Apartment.objects.count() == 1


def test_bulk_delete_is_protected_by_readings_too(apartment):
    MeterReading.objects.create(apartment_id=apartment.pk, period=PERIOD,
                                resource="cold_water", value=Decimal("110"))

    with pytest.raises(ProtectedError):
        Apartment.objects.filter(pk=apartment.pk).delete()

    assert Apartment.objects.count() == 1


@pytest.mark.parametrize("attach, expected", [
    pytest.param(
        lambda a: Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                                       initial_value=Decimal("100")),
        "приборы учёта", id="meter"),
    pytest.param(
        lambda a: MeterReading.objects.create(
            apartment_id=a.pk, period=PERIOD, resource="cold_water",
            value=Decimal("110")),
        "показания счётчиков", id="reading"),
])
def test_the_refusal_names_what_holds_the_apartment(apartment, attach, expected):
    """Отказ обязан называть причину: владелец должен понять, что убрать."""
    attach(apartment)

    with pytest.raises(ProtectedError) as refusal:
        apartment.delete()

    assert expected in str(refusal.value)


def test_an_apartment_without_history_still_deletes(apartment):
    """Защищается история, а не сама запись: опечатка в списке объектов
    остаётся исправимой."""
    apartment.delete()

    assert Apartment.objects.count() == 0


@pytest.mark.parametrize("attach", [
    pytest.param(
        lambda a: Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                                       initial_value=Decimal("100")),
        id="meter"),
    pytest.param(
        lambda a: MeterReading.objects.create(
            apartment_id=a.pk, period=PERIOD, resource="cold_water",
            value=Decimal("110")),
        id="reading"),
])
def test_a_neighbours_history_does_not_hold_this_apartment(apartment, attach):
    """Проверка обязана смотреть на историю **этой** квартиры. Без фильтра
    любая заведённая где-либо строка запирала бы весь список объектов."""
    neighbour = Apartment.objects.create(label="кв. 2")
    attach(neighbour)

    apartment.delete()

    assert set(Apartment.objects.values_list("pk", flat=True)) == {neighbour.pk}
