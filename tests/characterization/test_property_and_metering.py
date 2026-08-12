"""Объект и приборы учёта: пункты №29, №32 и №9 гап-анализа.

| Пункт | Что зафиксировано                                       | Кто перепишет |
|-------|---------------------------------------------------------|---------------|
| №29   | квартира с ГВС и нулевым нормативом начисляет ноль       | C3            |
| №32   | состав приборов выводится из флагов, а не из реестра     | C2            |
| №9    | удаление квартиры без жильца уносит показания и счета    | C3            |

№9 не помечен ⚠ — он проявится не у пользователя, а в данных. Тест здесь
потому, что план миграции назвал его одним из трёх мест, не покрытых
проверками вовсе.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError

from billing.models import (
    Apartment, Meter, MeterReading, MonthlyStatement, Tariff, Tenant,
)
from billing.services.statements import (
    MissingBaselineError, generate_statement, meters_for,
)

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]

PERIOD = date(2026, 7, 1)


def _tariff(code, rate):
    Tariff.objects.create(utility_type=code, rate=Decimal(rate),
                          effective_from=date(2020, 1, 1))


# --------------------------------------------------------------------------
# №29 — молчаливый ноль за подогрев. Переписывает шаг C3.
# --------------------------------------------------------------------------

def test_new_apartment_with_hot_water_charges_zero_for_heating():
    """Строка «подогрев» в счёте есть, количество ноль, сумма ноль, ошибки нет.

    `has_hot_water` по умолчанию `True`, `gvs_heat_norm` — `0`; владелец,
    заведший квартиру и не открывший квитанцию УК, недоначисляет и не узнаёт
    об этом. После C3 (ADR-0007) норматив при подведённой ГВС обязателен и
    больше нуля — этот тест переписывается на ожидание ошибки валидации, **и
    суммы новых счетов вырастут**.
    """
    apartment = Apartment.objects.create(label="кв", has_cold_water=False,
                                         has_hot_water=True, has_sewage=False)
    assert apartment.gvs_heat_norm == Decimal("0")
    apartment.full_clean()   # сегодня такая квартира считается корректной

    Meter.objects.create(apartment=apartment, kind="hot_water", initial_value=Decimal("50"))
    Meter.objects.create(apartment=apartment, kind="electricity_single",
                         initial_value=Decimal("1400"))
    _tariff("hot_water_cold_component", "25.86")
    _tariff("hot_water_heat_component", "2389.72")
    _tariff("electricity_single", "4.87")
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="hot_water", value=Decimal("55"))
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="electricity_single", value=Decimal("1500"))

    invoice = generate_statement(apartment, PERIOD)

    lines = {line["code"]: line for line in invoice.lines}
    assert lines["hot_water_heat_component"]["quantity"] == "0.00000"
    assert lines["hot_water_heat_component"]["amount"] == "0.00"
    # 5 м³ × 25.86 = 129.30 за объём, 0.00 за подогрев, 100 кВт·ч × 4.87 = 487.00
    assert invoice.total == Decimal("616.30")


# --------------------------------------------------------------------------
# №32 — два источника истины о составе приборов. Переписывает шаг C2.
# --------------------------------------------------------------------------

def test_registered_meter_outside_the_flags_is_never_billed():
    """Прибор заведён в реестре, но флага нет — в счёт он не попадает.

    После C2 состав определяет реестр приборов, а флаги `has_*` исчезают.
    """
    apartment = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Meter.objects.create(apartment=apartment, kind="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment=apartment, kind="electricity_single",
                         initial_value=Decimal("1400"))
    Meter.objects.create(apartment=apartment, kind="hot_water",   # заведён и забыт
                         serial_number="HW-1", initial_value=Decimal("50"))
    _tariff("cold_water", "48.15")
    _tariff("electricity_single", "4.87")
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="electricity_single", value=Decimal("1500"))

    assert meters_for(apartment) == ["cold_water", "electricity_single"]

    invoice = generate_statement(apartment, PERIOD)
    assert {line["code"] for line in invoice.lines} == {"cold_water", "electricity_single"}


def test_flag_without_registered_meter_stops_the_calculation():
    """Обратное расхождение тех же двух источников — и расчёт встаёт.

    `MissingBaselineError` существует именно потому, что состав берётся из
    флагов, а базы отсчёта — из реестра. После C2 источник один, и причина
    исключения исчезает вместе с расхождением.
    """
    apartment = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    _tariff("cold_water", "48.15")
    _tariff("electricity_single", "4.87")
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="electricity_single", value=Decimal("1500"))

    with pytest.raises(MissingBaselineError):
        generate_statement(apartment, PERIOD)


# --------------------------------------------------------------------------
# №9 — каскад на квартире. Переписывает шаг C3.
# --------------------------------------------------------------------------

def test_deleting_an_apartment_without_a_tenant_erases_its_whole_history():
    """Квартира без жильца удаляется бесшумно, унося показания и счета.

    `PROTECT` стоит только на жильце; на приборах, показаниях и счетах —
    `CASCADE`. После C3 удаление объекта запрещено вовсе, его место занимает
    вывод из эксплуатации.
    """
    apartment = Apartment.objects.create(label="кв")
    Meter.objects.create(apartment=apartment, kind="cold_water", initial_value=Decimal("100"))
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="cold_water", value=Decimal("110"))
    MonthlyStatement.objects.create(apartment=apartment, period=PERIOD,
                                    total=Decimal("1000.00"))

    apartment.delete()   # ни предупреждения, ни ошибки

    assert not Meter.objects.exists()
    assert not MeterReading.objects.exists()
    assert not MonthlyStatement.objects.exists()


def test_deleting_an_apartment_with_a_tenant_is_refused():
    """Единственная защита сегодня — живой жилец.

    Она же и обманчива: жильца удалить можно, после чего защиты не остаётся.
    """
    apartment = Apartment.objects.create(label="кв")
    user = User.objects.create_user("ivanov", password="pass12345")
    Tenant.objects.create(user=user, apartment=apartment, full_name="Иванов")

    with pytest.raises(ProtectedError):
        apartment.delete()
