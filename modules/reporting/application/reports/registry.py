"""Отчёт «Реестр»: текущее состояние — по листу на сущность."""

from modules.metering import api as metering
from modules.properties import api as properties
from modules.tenancy import api as tenancy

from ...infrastructure import xlsx


def build(run, stamp, params):
    flats = properties.list_properties(include_decommissioned=True)

    property_rows = [["Объект", "Наименование", "Адрес", "Эксплуатация"]]
    tenancy_rows = [["Объект", "Жилец", "Заселение", "Выезд",
                     "Аренда", "Интернет", "Прочее", "Дата подтверждена"]]
    meter_rows = [["Объект", "Ресурс", "Заводской номер", "Начальное показание"]]

    for flat in flats:
        property_rows.append([
            flat.apartment_id, flat.label, flat.address,
            "действует" if flat.decommissioned_on is None
            else f"выведен {flat.decommissioned_on:%d.%m.%Y}"])
        for contract in tenancy.list_tenancies_for(flat.apartment_id):
            tenancy_rows.append([
                flat.label, contract.full_name, contract.started_on,
                contract.ended_on or "", contract.terms.rent,
                contract.terms.internet, contract.terms.other_fixed,
                "да" if contract.start_confirmed else "нет"])
        for meter in metering.get_expected_meters(flat.apartment_id):
            meter_rows.append([flat.label, meter.resource,
                               meter.serial_number or "", meter.initial_value])

    payload = xlsx.workbook(stamp, [
        ("Объекты", property_rows), ("Договоры", tenancy_rows),
        ("Приборы", meter_rows)])
    return f"registry_{stamp:%Y%m%d_%H%M}.xlsx", payload
