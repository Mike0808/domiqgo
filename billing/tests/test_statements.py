from datetime import date
from decimal import Decimal
import pytest
from modules.metering.infrastructure.models import Meter, MeterReading
from billing.models import Apartment, MonthlyStatement
from modules.tariffs.api import publish_tariff_version
from billing.services.statements import (
    generate_statement, metered_resources, missing_meters,
)

pytestmark = pytest.mark.django_db

def _tariffs(effective=date(2026, 7, 1)):
    data = {"cold_water": "48.15", "hot_water_cold_component": "25.86",
            "hot_water_heat_component": "2389.72", "sewage": "36.40",
            "electricity_single": "4.87"}
    for code, rate in data.items():
        publish_tariff_version(utility=code, rate=Decimal(rate), effective_from=effective)

def _meters(apt, cold="0", hot="0", elec="0"):
    """Реестр приборов квартиры.

    С шага C2e без него не начисляется ничто: состав задаёт реестр, а не
    флаги. Раньше эти строки в тестах были не нужны — база отсчёта бралась из
    показаний прошлого периода, а список приборов выводился из карточки.
    """
    for resource, initial in (("cold_water", cold), ("hot_water", hot),
                              ("electricity_single", elec)):
        Meter.objects.create(apartment_id=apt.pk, resource=resource,
                             initial_value=Decimal(initial))

def _readings(apt, period, cold, hot, elec):
    MeterReading.objects.create(apartment_id=apt.pk, period=period, resource="cold_water", value=Decimal(cold))
    MeterReading.objects.create(apartment_id=apt.pk, period=period, resource="hot_water", value=Decimal(hot))
    MeterReading.objects.create(apartment_id=apt.pk, period=period, resource="electricity_single", value=Decimal(elec))

def test_metered_resources_come_from_the_registry_not_the_flags():
    """Шаг C2e. Прежде этот тест назывался `test_meters_for_single_vs_dual` и
    проверял обратное: состав выводился из флагов квартиры и типа
    электросчётчика, а реестр приборов не спрашивали вовсе."""
    a = Apartment.objects.create(label="кв", electricity_meter_type=Apartment.SINGLE)

    assert metered_resources(a) == []          # флаги обещают, реестр пуст

    Meter.objects.create(apartment_id=a.pk, resource="electricity_day",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_night",
                         initial_value=Decimal("0"))

    # Тип счётчика в карточке — «однотарифный», но заведены два прибора, и
    # начисляться будут они: реестр знает, что стоит в квартире, карточка — нет.
    assert metered_resources(a) == ["electricity_day", "electricity_night"]

def test_generate_uses_previous_period_as_baseline():
    a = Apartment.objects.create(label="кв", rent=Decimal("20000"), internet=Decimal("700"),
                                 gvs_heat_norm=Decimal("0.05229"))
    _tariffs()
    _meters(a)
    _readings(a, date(2026, 6, 1), "100", "50", "1400")
    _readings(a, date(2026, 7, 1), "110", "55", "1500")

    stmt = generate_statement(a, date(2026, 7, 1))

    assert stmt.total == Decimal("22950.00")   # 22968.59 floored to 50
    by = {l["code"]: l for l in stmt.lines}
    assert by["rounding"]["amount"] == "-18.59"
    assert by["cold_water"]["amount"] == "481.50"
    assert by["hot_water_cold_component"]["amount"] == "129.30"    # 5 * 25.86
    assert by["hot_water_heat_component"]["quantity"] == "0.26145"  # 5 * 0.05229 Гкал
    assert by["hot_water_heat_component"]["amount"] == "624.79"
    assert by["sewage"]["amount"] == "546.00"
    assert by["rent"]["quantity"] is None

def test_generate_selects_tariff_effective_for_period():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False,
                                 electricity_meter_type=Apartment.SINGLE)
    publish_tariff_version(utility="cold_water", rate=Decimal("40.00"), effective_from=date(2025, 7, 1))
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2025, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), resource="cold_water", value=Decimal("100"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), resource="electricity_single", value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("0"))

    june = generate_statement(a, date(2026, 6, 1))   # baseline: contract initials
    july = generate_statement(a, date(2026, 7, 1))   # baseline: June readings

    july_cold = {l["code"]: l for l in july.lines}["cold_water"]
    assert july_cold["rate"] == "48.1500"            # new tariff applied for July
    assert july_cold["amount"] == "481.50"           # (110-100) * 48.15

def test_generate_is_idempotent_and_keeps_status():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))
    stmt.status = MonthlyStatement.PAID
    stmt.save()
    again = generate_statement(a, date(2026, 7, 1))
    assert again.pk == stmt.pk
    assert again.status == MonthlyStatement.PAID
    assert MonthlyStatement.objects.filter(apartment=a, period=date(2026, 7, 1)).count() == 1

def test_first_month_baseline_comes_from_meter_initial_values():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    # values fixed in the act at contract signing
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", serial_number="CW-1",
                         initial_value=Decimal("100"), initial_date=date(2026, 6, 15))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", serial_number="E-1",
                         initial_value=Decimal("1400"), initial_date=date(2026, 6, 15))
    # tenant's very first submission — no prior-month readings exist
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))

    # (110-100)*48.15 + (1500-1400)*4.87 = 968.50 — below 10 000, not rounded
    assert stmt.total == Decimal("968.50")

def test_baseline_falls_back_per_meter():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("1400"))
    # June has a reading for electricity only; cold water must fall back to the initial value
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), resource="electricity_single", value=Decimal("1450"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))

    # cold: (110-100)*48.15 = 481.50; elec: (1500-1450)*4.87 = 243.50 — not rounded
    assert stmt.total == Decimal("725.00")

def test_without_registered_meters_nothing_metered_is_billed():
    """Шаг C2e: состав задаёт реестр приборов.

    До него этот случай останавливал расчёт (`MissingBaselineError`): состав
    брался из флагов, а базы отсчёта — из реестра, и они расходились. Теперь
    источник один, и расхождению неоткуда взяться: нет прибора — нечего
    начислять по счётчику.

    Ответственность за состав приборов несёт владелец, поэтому расчёт не
    встаёт. Чтобы это не превратилось в тихое недоначисление, ему видно, чего
    не хватает, — см. `missing_meters` и столбец в списке квартир.
    """
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    # ни одного прибора в реестре — только показания, взявшиеся ниоткуда
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))

    assert [line["code"] for line in stmt.lines] == []
    assert stmt.total == Decimal("0.00")
    assert missing_meters(a) == ["cold_water", "electricity_single"]


# ------------------------------------------------- сверка флагов с реестром

def test_missing_meters_lists_what_the_flags_promise_but_the_registry_lacks():
    """Шаг C2e: расчёт не встаёт, но расхождение владельцу видно.

    Иначе счёт без горячей воды выглядел бы законным и недоначислял незаметно
    — ровно то, что делал нулевой норматив подогрева до исправления №29.
    """
    a = Apartment.objects.create(label="кв")   # ХВС, ГВС и однотарифный свет

    assert missing_meters(a) == ["cold_water", "hot_water", "electricity_single"]


def test_a_registered_meter_disappears_from_the_warning():
    a = Apartment.objects.create(label="кв", has_hot_water=False)
    Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                         initial_value=Decimal("0"))

    assert missing_meters(a) == ["electricity_single"]


def test_nothing_is_missing_when_the_registry_covers_the_flags():
    a = Apartment.objects.create(label="кв", has_hot_water=False)
    Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single",
                         initial_value=Decimal("0"))

    assert missing_meters(a) == []


def test_a_dual_meter_apartment_wants_both_zones():
    a = Apartment.objects.create(label="кв", has_cold_water=False,
                                 has_hot_water=False,
                                 electricity_meter_type=Apartment.DUAL)
    Meter.objects.create(apartment_id=a.pk, resource="electricity_day",
                         initial_value=Decimal("0"))

    assert missing_meters(a) == ["electricity_night"]


def test_a_meter_outside_the_flags_is_not_a_shortage():
    """Лишний прибор — не нехватка: он просто начисляется. Сверка смотрит в
    одну сторону, потому что вторая перестала быть расхождением."""
    a = Apartment.objects.create(label="кв", has_cold_water=False,
                                 has_hot_water=False,
                                 electricity_meter_type=Apartment.SINGLE)
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="hot_water",
                         initial_value=Decimal("0"))

    assert missing_meters(a) == []


# ------------------------------- конфигурацию объекта спрашивают у Properties

def test_the_bill_takes_the_service_composition_from_properties():
    """Проверяется не результат, а путь — и другого способа нет.

    Прямое чтение `apartment.has_sewage` даёт тот же ответ: это одна и та же
    строка одной и той же таблицы, и разойтись двум чтениям негде. Мутация
    «читать поле напрямую» прошла зелёной, пока этот тест не появился.
    Поэтому здесь подменяется сам публичный API модуля: если Billing к нему не
    обратится, подмена не подействует.
    """
    from unittest.mock import patch
    from modules.properties.domain import Apartment as PropertyView

    a = Apartment.objects.create(label="кв", has_sewage=True,
                                 gvs_heat_norm=Decimal("0.05229"))
    _tariffs()
    _meters(a)
    _readings(a, date(2026, 7, 1), "110", "55", "1500")
    without_sewage = PropertyView(
        apartment_id=a.pk, label="кв", has_cold_water=True, has_hot_water=True,
        has_sewage=False, gvs_heat_norm=Decimal("0.05229"))

    with patch("billing.services.statements.properties.get_property",
               return_value=without_sewage):
        stmt = generate_statement(a, date(2026, 7, 1))

    assert "sewage" not in {line["code"] for line in stmt.lines}


def test_the_meter_reconciliation_asks_properties_too():
    """`missing_meters` сверяет реестр приборов с составом услуг объекта —
    и состав тоже берёт у модуля, а не из строки под рукой."""
    from unittest.mock import patch
    from modules.properties.domain import Apartment as PropertyView

    a = Apartment.objects.create(label="кв", has_hot_water=False)
    only_hot_water = PropertyView(
        apartment_id=a.pk, label="кв", has_cold_water=False, has_hot_water=True,
        has_sewage=False, gvs_heat_norm=Decimal("0.05229"))

    with patch("billing.services.statements.properties.get_property",
               return_value=only_hot_water):
        missing = missing_meters(a)

    assert "hot_water" in missing
