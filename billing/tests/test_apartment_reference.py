"""Объект недвижимости в `billing/`: форма ввода и вывод из эксплуатации.

Приборы и показания уехали в Metering на C2, правила учёта — следом. Здесь
осталось то, что относится к самому объекту:

- удаления объекта нет как операции, есть вывод из эксплуатации (шаг **C3a**);
- форма ввода показаний, которую собирает представление из реестра приборов.

Изоляция точек учёта, база отсчёта и монотонность проверяются в
`tests/metering/`: правила там, где живут. Файл переедет в `tests/properties/`
шагом **C3b** вместе с самой моделью.
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
from modules.properties import api as properties
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
    Tenant.objects.create(user=user, apartment=apartment, full_name="Жилец")
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


# --------------------------------- вывод из эксплуатации вместо удаления

def test_an_apartment_is_never_deleted(apartment):
    """Шаг C3a: удаления объекта нет как операции — ни для квартиры с
    историей, ни для пустой."""
    with pytest.raises(ProtectedError):
        apartment.delete()

    assert Apartment.objects.count() == 1


def test_bulk_delete_from_the_list_is_refused_too(apartment):
    """`queryset.delete()` — путь, которым удаляет админка, выделив объекты
    галочками. Переопределения `Model.delete` он не касается."""
    with pytest.raises(ProtectedError):
        Apartment.objects.filter(pk=apartment.pk).delete()

    assert Apartment.objects.count() == 1


def test_the_refusal_says_what_to_do_instead(apartment):
    with pytest.raises(ProtectedError) as refusal:
        apartment.delete()

    assert "выведите его из эксплуатации" in str(refusal.value).lower()
    assert "история останется" in str(refusal.value).lower()


def test_a_new_apartment_is_in_service(apartment):
    assert properties.get_property(apartment.pk).in_service is True
    assert apartment.decommissioned_on is None


def test_decommissioning_records_the_date(apartment):
    """Датой, а не флагом: владельцу важно, с какого числа объект перестал
    сдаваться, а отчёту за прошлый год — что тогда он ещё сдавался."""
    properties.decommission_property(apartment.pk, date(2026, 7, 15))

    assert properties.get_property(apartment.pk).in_service is False
    assert Apartment.objects.get().decommissioned_on == date(2026, 7, 15)


def test_decommissioning_defaults_to_today(apartment):
    properties.decommission_property(apartment.pk, timezone.localdate())

    assert Apartment.objects.get().decommissioned_on == timezone.localdate()


def test_decommissioning_keeps_the_history(apartment):
    """Смысл операции: объект уходит из списка действующих, история остаётся."""
    Meter.objects.create(apartment_id=apartment.pk, resource="cold_water",
                         initial_value=Decimal("100"))
    MeterReading.objects.create(apartment_id=apartment.pk, period=PERIOD,
                                resource="cold_water", value=Decimal("110"))

    properties.decommission_property(apartment.pk, timezone.localdate())

    assert Meter.objects.count() == 1
    assert MeterReading.objects.count() == 1


def test_recommissioning_returns_it_to_service(apartment):
    """Ошибиться можно и здесь, и тупика быть не должно."""
    properties.decommission_property(apartment.pk, timezone.localdate())

    properties.recommission_property(apartment.pk)

    assert Apartment.objects.get().decommissioned_on is None
    assert properties.get_property(apartment.pk).in_service is True


def test_decommissioning_one_leaves_the_neighbour_in_service(apartment):
    neighbour = Apartment.objects.create(label="кв. 2")

    properties.decommission_property(apartment.pk, timezone.localdate())

    assert properties.get_property(neighbour.pk).in_service is True
