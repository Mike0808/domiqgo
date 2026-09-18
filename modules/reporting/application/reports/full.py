"""«Полная выгрузка»: всё, включая историю; документы — только метаданные.

Гарантия «свободы уйти», а не резервная копия (ADR-0021): восстановление из
неё не предусмотрено, и она не согласованный снимок.
"""

from modules.billing import api as billing
from modules.metering import api as metering
from modules.payments import api as payments
from modules.properties import api as properties
from modules.tariffs import api as tariffs
from modules.tenancy import api as tenancy

from . import documents_meta
from .jsonutil import dumps


def tenancy_row(contract) -> dict:
    return {
        "tenancy_id": contract.tenancy_id, "account_id": contract.account_id,
        "full_name": contract.full_name, "started_on": contract.started_on,
        "ended_on": contract.ended_on,
        "start_confirmed": contract.start_confirmed,
        "terms": {"rent": contract.terms.rent,
                  "internet": contract.terms.internet,
                  "other_fixed": contract.terms.other_fixed},
    }


def build(run, stamp, params):
    flats = properties.list_properties(include_decommissioned=True)
    contracts = [c for flat in flats
                 for c in tenancy.list_tenancies_for(flat.apartment_id)]
    payload = {
        "generated_at": stamp,
        "properties": [{
            "property_id": flat.apartment_id, "label": flat.label,
            "address": flat.address,
            "decommissioned_on": flat.decommissioned_on,
        } for flat in flats],
        "tenancies": [tenancy_row(c) for c in contracts],
        "meters": [{
            "property_id": flat.apartment_id, "resource": meter.resource,
            "serial_number": meter.serial_number,
            "initial_value": meter.initial_value,
        } for flat in flats
            for meter in metering.get_expected_meters(flat.apartment_id)],
        "readings": [dict(row, property_id=flat.apartment_id)
                     for flat in flats
                     for row in metering.list_readings(flat.apartment_id)],
        "tariffs": [{
            "utility": code, "rate": rate.rate,
            "effective_from": rate.effective_from,
        } for code in tariffs.utilities()
            for rate in tariffs.list_versions(code)],
        "invoices": billing.list_invoice_rows(),
        "payments": payments.list_payments(),
        "documents": [dict(meta, tenancy_id=c.tenancy_id)
                      for c in contracts
                      for meta in documents_meta(c.tenancy_id)],
    }
    return f"full_{stamp:%Y%m%d_%H%M}.json", dumps(payload)
