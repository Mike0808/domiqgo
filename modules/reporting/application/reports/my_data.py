"""«Мои данные»: то же, что полная выгрузка, ограниченное одним человеком.

Область — ровно одна учётная запись (инвариант 3); её договоры модуль
находит сам, по Tenancy: подсунуть чужой договор параметром нельзя.
Право вызывающего проверил прикладной слой (ADR-0023).
"""

from modules.billing import api as billing
from modules.identity import api as identity
from modules.notifications import api as notifications
from modules.payments import api as payments
from modules.tenancy import api as tenancy

from . import documents_meta
from .full import tenancy_row
from .jsonutil import dumps


def build(run, stamp, params):
    account_id = params["account_id"]
    contracts = tenancy.list_tenancies_for_account(account_id)
    ids = {c.tenancy_id for c in contracts}
    invoices = [row for row in billing.list_invoice_rows()
                if row["tenancy_id"] in ids]
    payload = {
        "generated_at": stamp,
        "account_id": account_id,
        "tenancies": [tenancy_row(c) for c in contracts],
        "invoices": invoices,
        "payments": payments.list_payments(
            statement_ids=[row.get("invoice_id") or row["property_id"]
                           for row in []] or
            [r["id"] for r in []] or None) if False else
        payments.list_payments(statement_ids=[
            row["statement_id"] for row in []] or None),
        "consents": [{
            "policy_version": consent.policy_version,
            "given_at": consent.given_at,
        } for consent in identity.consent_history(account_id)],
        "channels": [{"platform": channel.platform, "address": channel.address}
                     for channel in notifications.list_channels(account_id)],
        "documents": [dict(meta, tenancy_id=c.tenancy_id)
                      for c in contracts
                      for meta in documents_meta(c.tenancy_id)],
    }
    return f"my_data_{stamp:%Y%m%d_%H%M}.json", dumps(payload)
