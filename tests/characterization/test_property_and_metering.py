"""Объект и приборы учёта: пункты №29, №32 и №9 гап-анализа.

| Пункт | Что зафиксировано                                       | Кто перепишет |
|-------|---------------------------------------------------------|---------------|
| №29   | ~~квартира с ГВС и нулевым нормативом начисляет ноль~~ исправлен | — (C3) |
| №32   | состав приборов выводится из флагов, а не из реестра     | C2            |
| №9    | ~~удаление квартиры уносит показания и счета~~ исправлен | — (C3)        |

№9 не помечен ⚠ — он проявился бы не у пользователя, а в данных. Тест здесь
потому, что план миграции назвал его одним из трёх мест, не покрытых
проверками вовсе. Исправлен до начала этапа B (миграция 0007): `on_delete`
на приборах, показаниях и счетах переведён с `CASCADE` на `PROTECT`, тесты
переписаны здесь же. C3 вернётся к нему ещё раз — заменить удаление объекта
выводом из эксплуатации.

№29 исправлен там же и тогда же ([ADR-0026](../../docs/architecture/adr/0026-defect-fixes-allowed-in-legacy-app.md)):
норматив подогрева обязателен при подведённой ГВС, расчёт отказывается вместо
нулевой строки. C3 перенесёт инвариант в Properties, но правило уже действует.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from billing.models import (
    Apartment, Meter, MeterReading, MonthlyStatement, Tariff, Tenant,
)
from billing.services.calculation import MissingHeatNormError
from billing.services.statements import (
    MissingBaselineError, generate_statement, meters_for,
)

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]

PERIOD = date(2026, 7, 1)


def _tariff(code, rate):
    Tariff.objects.create(utility_type=code, rate=Decimal(rate),
                          effective_from=date(2020, 1, 1))


# --------------------------------------------------------------------------
# №29 — молчаливый ноль за подогрев. Дефект исправлен. Переписан.
# --------------------------------------------------------------------------
#
# Тест до исправления назывался
# `test_new_apartment_with_hot_water_charges_zero_for_heating` и утверждал,
# что счёт выставляется, строка «подогрев» в нём есть, количество `"0.00000"`,
# сумма `"0.00"`, итог 616.30 ₽ — и никакой ошибки. Переписан тем же коммитом,
# что и проверка, так требует контракт каталога.


def _hot_water_apartment(norm):
    apartment = Apartment.objects.create(
        label="кв", has_cold_water=False, has_hot_water=True, has_sewage=False,
        gvs_heat_norm=Decimal(norm))
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
    return apartment


def test_apartment_with_hot_water_and_no_norm_is_rejected_by_validation():
    """Квартиру с подведённой ГВС и незаполненным нормативом нельзя сохранить.

    Раньше `has_hot_water` по умолчанию `True` при `gvs_heat_norm` по умолчанию
    `0` считалось корректной конфигурацией, и владелец, не открывший квитанцию
    УК, недоначислял молча. Инвариант из ADR-0007.
    """
    apartment = Apartment(label="кв", has_hot_water=True)
    assert apartment.gvs_heat_norm == Decimal("0")

    with pytest.raises(ValidationError) as exc:
        apartment.full_clean()
    assert "gvs_heat_norm" in exc.value.error_dict

    apartment.has_hot_water = False
    apartment.full_clean()   # без ГВС норматив не нужен


def test_statement_refuses_to_hide_the_missing_norm_behind_a_zero():
    """Расчёт отказывается, а не выставляет счёт с нулевым подогревом.

    `Model.clean` не вызывается при `objects.create` и не защищает квартиры,
    заведённые до исправления, — поэтому у расчёта своя проверка. Прежний счёт
    на 616.30 ₽ (129.30 за объём + 0.00 за подогрев + 487.00 за свет) больше
    не выставляется вовсе.
    """
    apartment = _hot_water_apartment("0")

    with pytest.raises(MissingHeatNormError):
        generate_statement(apartment, PERIOD)

    assert not MonthlyStatement.objects.exists()


def test_the_same_apartment_with_a_norm_bills_the_heating():
    """**Суммы вырастут**: те же показания с заполненным нормативом.

    Разница между 616.30 и 916.81 ₽ — 300.51 ₽ за один месяц по одной
    квартире — и есть то, что дефект отдавал бесплатно.
    """
    apartment = _hot_water_apartment("0.02515")

    invoice = generate_statement(apartment, PERIOD)

    lines = {line["code"]: line for line in invoice.lines}
    # 5 м³ × 0.02515 = 0.12575 Гкал × 2389.72 ₽/Гкал = 300.51 ₽
    assert lines["hot_water_heat_component"]["quantity"] == "0.12575"
    assert lines["hot_water_heat_component"]["amount"] == "300.51"
    # 129.30 за объём + 300.51 за подогрев + 487.00 за свет
    assert invoice.total == Decimal("916.81")


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
# №9 — каскад на квартире. Дефект исправлен: миграция 0007. Переписан.
# --------------------------------------------------------------------------
#
# Тест до исправления назывался
# `test_deleting_an_apartment_without_a_tenant_erases_its_whole_history` и
# утверждал обратное: `apartment.delete()` проходит молча, а `Meter`,
# `MeterReading` и `MonthlyStatement` после него не существуют. Переименован
# и переписан в том же коммите, что и `on_delete` — так требует контракт
# каталога.

def test_deleting_an_apartment_with_history_is_refused():
    """Квартира, за которой стоят приборы, показания или счета, не удаляется.

    Прежде на всех трёх стоял `CASCADE`, и удаление квартиры уносило историю
    начислений целиком — без предупреждения и без следа. Теперь `PROTECT`, и
    удаление падает на первой же связи.

    Это не полный запрет удаления: пустая, ни разу не начислявшаяся квартира
    удаляется по-прежнему (см. тест ниже). Замена удаления на вывод из
    эксплуатации — шаг C3 плана миграции, и он перепишет уже этот тест.
    """
    apartment = Apartment.objects.create(label="кв")
    Meter.objects.create(apartment=apartment, kind="cold_water", initial_value=Decimal("100"))
    MeterReading.objects.create(apartment=apartment, period=PERIOD,
                                meter="cold_water", value=Decimal("110"))
    MonthlyStatement.objects.create(apartment=apartment, period=PERIOD,
                                    total=Decimal("1000.00"))

    with pytest.raises(ProtectedError):
        apartment.delete()

    assert Meter.objects.count() == 1
    assert MeterReading.objects.count() == 1
    assert MonthlyStatement.objects.count() == 1


@pytest.mark.parametrize(
    "attach",
    [
        pytest.param(
            lambda a: Meter.objects.create(apartment=a, kind="cold_water",
                                           initial_value=Decimal("100")),
            id="meter",
        ),
        pytest.param(
            lambda a: MeterReading.objects.create(apartment=a, period=PERIOD,
                                                  meter="cold_water",
                                                  value=Decimal("110")),
            id="reading",
        ),
        pytest.param(
            lambda a: MonthlyStatement.objects.create(apartment=a, period=PERIOD,
                                                      total=Decimal("1000.00")),
            id="statement",
        ),
    ],
)
def test_each_kind_of_history_protects_the_apartment_on_its_own(attach):
    """Каждая из трёх связей держит квартиру сама, а не только все вместе."""
    apartment = Apartment.objects.create(label="кв")
    attach(apartment)

    with pytest.raises(ProtectedError):
        apartment.delete()


def test_an_apartment_that_was_never_used_still_deletes():
    """Опечатка в списке объектов остаётся исправимой.

    `PROTECT` защищает историю, а не саму запись: квартира без приборов,
    показаний, счетов и жильцов удаляется без возражений.
    """
    apartment = Apartment.objects.create(label="опечатка")

    apartment.delete()

    assert not Apartment.objects.exists()


def test_deleting_an_apartment_with_a_tenant_is_refused():
    """Защита жильцом была и остаётся; теперь она не единственная.

    Раньше её можно было снять, удалив жильца, — после чего история уходила
    вместе с квартирой. Теперь удаление жильца оставляет квартиру защищённой
    её собственными начислениями.
    """
    apartment = Apartment.objects.create(label="кв")
    user = User.objects.create_user("ivanov", password="pass12345")
    Tenant.objects.create(user=user, apartment=apartment, full_name="Иванов")

    with pytest.raises(ProtectedError):
        apartment.delete()
