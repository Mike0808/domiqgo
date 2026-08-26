from datetime import date
from decimal import Decimal
import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client
from modules.metering.infrastructure.models import Meter, MeterReading
from modules.properties import api as properties
from billing.models import Apartment, MonthlyStatement
from modules.tariffs.api import publish_tariff_version

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_client():
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    c = Client()
    c.login(username="boss", password="pass12345")
    return c

def test_admin_apartment_changelist_loads(admin_client):
    Apartment.objects.create(label="кв. 10")
    resp = admin_client.get("/admin/properties/apartment/")
    assert resp.status_code == 200

def test_regenerate_action_recomputes_total(admin_client):
    
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    })
    stmt.refresh_from_db()
    # New meters start at 0: 110*48.15 + 1600*4.87 = 13088.50 -> floored to 13050
    assert stmt.total == Decimal("13050.00")

def test_regenerate_action_reports_failure_without_500(admin_client):
    
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=True)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))  # sewage tariff missing
    resp = admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    }, follow=True)
    assert resp.status_code == 200  # reported via messages, not a 500

def test_admin_saving_reading_recalculates_statement(admin_client):
    
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("1400"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))
    resp = admin_client.post("/admin/metering/meterreading/add/", {
        "apartment_id": str(a.pk), "period": "2026-07-01",
        "resource": "cold_water", "value": "110",
    }, follow=True)
    assert resp.status_code == 200
    stmt = MonthlyStatement.objects.get(apartment=a, period=date(2026, 7, 1))
    assert stmt.total == Decimal("968.50")  # recalculated on save; below 10 000 — not rounded


# ------------------------------- предупреждение о незаведённых приборах (C2e)

def test_the_apartment_list_names_the_meters_to_register(admin_client):
    """Счёт чаще всего порождает жилец, сдавая показания, и сообщения того
    пересчёта владелец не увидит никогда. Поэтому нехватка видна в списке."""
    Apartment.objects.create(label="кв. 10", has_hot_water=False)

    page = admin_client.get("/admin/properties/apartment/").content.decode()

    assert "Холодная вода" in page
    assert "Электроэнергия" in page
    # Тип счётчика из карточки исчез: какой прибор стоит, знает реестр
    # (шаг C3d, ADR-0028).
    assert "Тип счётчика электроэнергии" not in page


def test_the_apartment_list_stays_quiet_when_the_registry_is_complete(admin_client):
    a = Apartment.objects.create(label="кв. 10", has_hot_water=False)
    Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single",
                         initial_value=Decimal("0"))

    page = admin_client.get("/admin/properties/apartment/").content.decode()

    assert "Холодная вода" not in page


def test_recalculating_warns_about_meters_that_are_not_registered(admin_client):
    a = Apartment.objects.create(label="кв. 10", has_hot_water=False,
                                 has_sewage=False)
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    resp = admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    }, follow=True)

    page = resp.content.decode()
    assert "не заведены приборы" in page
    assert "в счёт не попали" in page


# ------------------------- админка ходит через команды модуля (шаг C2f)

@pytest.mark.django_db(transaction=True)
def test_adding_a_meter_through_the_admin_announces_it(admin_client):
    """Админка — единственный способ завести прибор, и через обычный CRUD
    объявленное событие не наступало бы никогда. Тот же урок, что с тарифами
    на шаге C1a."""
    from bus import clear_subscribers, subscribe
    from modules.metering.events import MeterRegistered

    clear_subscribers()
    received = []
    subscribe(MeterRegistered, received.append)
    try:
        a = Apartment.objects.create(label="кв")
        resp = admin_client.post("/admin/metering/meter/add/", {
            "apartment_id": str(a.pk), "resource": "cold_water",
            "serial_number": "CW-1", "initial_value": "100",
            "initial_date": "",
        })

        assert resp.status_code == 302
        assert [e.resource for e in received] == ["cold_water"]
        assert Meter.objects.count() == 1
    finally:
        clear_subscribers()


@pytest.mark.django_db(transaction=True)
def test_editing_a_reading_through_the_admin_announces_a_correction(admin_client):
    from bus import clear_subscribers, subscribe
    from modules.metering.events import MeterReadingCorrected

    clear_subscribers()
    received = []
    subscribe(MeterReadingCorrected, received.append)
    try:
        a = Apartment.objects.create(label="кв", has_hot_water=False,
                                     has_sewage=False)
        reading = MeterReading.objects.create(
            apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water",
            value=Decimal("110"))

        admin_client.post(f"/admin/metering/meterreading/{reading.pk}/change/", {
            "apartment_id": str(a.pk), "period": "2026-07-01",
            "resource": "cold_water", "value": "115",
        })

        assert [(e.previous_value, e.new_value) for e in received] == [
            (Decimal("110.000"), Decimal("115.000"))]
        assert MeterReading.objects.get().value == Decimal("115.000")
    finally:
        clear_subscribers()


# ------------------- вывод из эксплуатации вместо удаления (шаг C3a)

def test_the_apartment_list_offers_no_delete_action(admin_client):
    """Кнопки удаления нет вовсе: владелец не должен упираться в отказ уже
    после подтверждения."""
    Apartment.objects.create(label="кв. 10")

    page = admin_client.get("/admin/properties/apartment/").content.decode()

    assert "delete_selected" not in page
    assert "Вывести из эксплуатации" in page


def test_the_change_form_offers_no_delete_button(admin_client):
    a = Apartment.objects.create(label="кв. 10")

    page = admin_client.get(f"/admin/properties/apartment/{a.pk}/change/").content.decode()

    assert "Удалить" not in page


def test_the_action_decommissions_and_warns_about_contracts(admin_client):
    """Действующий договор выводом не прекращается (ADR-0009), и владельцу об
    этом говорят: система не вправе отменять юридический факт из-за
    административной отметки."""
    a = Apartment.objects.create(label="кв. 10")

    resp = admin_client.post("/admin/properties/apartment/", {
        "action": "decommission_properties",
        "_selected_action": [str(a.pk)],
    }, follow=True)

    a.refresh_from_db()
    assert a.in_service is False
    page = resp.content.decode()
    assert "Выведено из эксплуатации: 1" in page
    assert "договоры не прекращены" in page


def test_the_action_returns_a_property_to_service(admin_client):
    a = Apartment.objects.create(label="кв. 10")
    properties.decommission_property(a.pk, timezone.localdate())

    admin_client.post("/admin/properties/apartment/", {
        "action": "recommission_properties",
        "_selected_action": [str(a.pk)],
    }, follow=True)

    a.refresh_from_db()
    assert a.in_service is True


def test_the_list_shows_the_service_state(admin_client):
    a = Apartment.objects.create(label="кв. 10")
    properties.decommission_property(a.pk, date(2026, 7, 15))

    page = admin_client.get("/admin/properties/apartment/").content.decode()

    assert "выведен 15.07.2026" in page


@pytest.mark.django_db(transaction=True)
def test_decommissioning_from_the_admin_announces_it(admin_client):
    """Вывод обязан идти командой модуля, а не правкой поля.

    Иначе `PropertyDecommissioned` не наступит, а на нём держится правило
    Tenancy «на выведенном объекте новых договоров не заключают» (ADR-0009).
    Проверка результата этого не ловит: правка поля даёт тот же выведенный
    объект — мутация «queryset.update вместо команды» прошла зелёной, пока
    этого теста не было.
    """
    from bus import clear_subscribers, subscribe
    from modules.properties.events import PropertyDecommissioned

    clear_subscribers()
    received = []
    subscribe(PropertyDecommissioned, received.append)
    try:
        a = Apartment.objects.create(label="кв. 10")

        admin_client.post("/admin/properties/apartment/", {
            "action": "decommission_properties",
            "_selected_action": [str(a.pk)],
        }, follow=True)

        assert [e.apartment_id for e in received] == [a.pk]
    finally:
        clear_subscribers()


@pytest.mark.django_db(transaction=True)
def test_recommissioning_from_the_admin_announces_it(admin_client):
    from bus import clear_subscribers, subscribe
    from modules.properties.events import PropertyRecommissioned

    clear_subscribers()
    received = []
    subscribe(PropertyRecommissioned, received.append)
    try:
        a = Apartment.objects.create(label="кв. 10")
        properties.decommission_property(a.pk, date(2026, 7, 15))

        admin_client.post("/admin/properties/apartment/", {
            "action": "recommission_properties",
            "_selected_action": [str(a.pk)],
        }, follow=True)

        assert [e.apartment_id for e in received] == [a.pk]
    finally:
        clear_subscribers()


# ------------------------- карточка объекта ходит через команды (шаг C3e)

@pytest.mark.django_db(transaction=True)
def test_adding_an_apartment_through_the_admin_announces_it(admin_client):
    """Карточка — единственный способ завести объект, и через обычный CRUD
    объявленное событие не наступило бы никогда."""
    from bus import clear_subscribers, subscribe
    from modules.properties.events import PropertyRegistered

    clear_subscribers()
    received = []
    subscribe(PropertyRegistered, received.append)
    try:
        resp = admin_client.post("/admin/properties/apartment/add/", {
            "label": "Ленина", "address": "Уфа, Ленина 1",
            "has_cold_water": "on", "has_sewage": "on",
            "gvs_heat_norm": "0", "round_total": "on",
            "rent": "20000", "internet": "700", "other_fixed": "0",
        })

        assert resp.status_code == 302
        assert [e.label for e in received] == ["Ленина"]
    finally:
        clear_subscribers()


def test_the_temporary_tenants_survive_the_command(admin_client):
    """Форма показывает поля трёх модулей сразу. Команда пишет своё, остаток
    дописывается следом — и не должен потеряться по дороге."""
    admin_client.post("/admin/properties/apartment/add/", {
        "label": "Ленина", "address": "", "has_cold_water": "on",
        "has_sewage": "on", "gvs_heat_norm": "0", "round_total": "on",
        "rent": "20000", "internet": "700", "other_fixed": "0",
    })

    stored = Apartment.objects.get()
    assert stored.rent == Decimal("20000.00")
    assert stored.internet == Decimal("700.00")
    assert stored.round_total is True


@pytest.mark.django_db(transaction=True)
def test_changing_the_composition_from_the_admin_announces_it(admin_client):
    from bus import clear_subscribers, subscribe
    from modules.properties.events import PropertyServiceCompositionChanged

    a = Apartment.objects.create(label="Ленина", has_hot_water=False)
    clear_subscribers()
    received = []
    subscribe(PropertyServiceCompositionChanged, received.append)
    try:
        admin_client.post(f"/admin/properties/apartment/{a.pk}/change/", {
            "label": "Ленина", "address": "", "has_cold_water": "on",
            "has_hot_water": "on", "has_sewage": "on",
            "gvs_heat_norm": "0.05229", "round_total": "on",
            "rent": "0", "internet": "0", "other_fixed": "0",
        })

        assert [(e.was_hot_water, e.now_hot_water) for e in received] == [(False, True)]
    finally:
        clear_subscribers()


def test_an_apartment_without_a_label_is_refused_by_the_form(admin_client):
    resp = admin_client.post("/admin/properties/apartment/add/", {
        "label": "", "address": "", "has_cold_water": "on",
        "gvs_heat_norm": "0", "round_total": "on",
        "rent": "0", "internet": "0", "other_fixed": "0",
    })

    assert resp.status_code == 200          # форма вернулась с ошибкой
    assert Apartment.objects.count() == 0
