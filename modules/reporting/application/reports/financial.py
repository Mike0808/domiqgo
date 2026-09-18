"""Отчёт «Финансовый за период»: начисления построчно и подтверждённые
платежи, сгруппированные по объектам. Итоги — формулами Excel."""

from modules.billing import api as billing
from modules.payments import api as payments
from modules.properties import api as properties

from ...infrastructure import xlsx


def build(run, stamp, params):
    """`params`: необязательные границы периода — месяцы `from`/`to`
    (date). Отчёт «за период», но пустые границы значат «за всё время»."""
    labels = {flat.apartment_id: flat.label
              for flat in properties.list_properties(include_decommissioned=True)}

    invoice_rows = [["Объект", "Период", "Строка", "Кол-во", "Ставка",
                     "Сумма", "Итог счёта", "Выставлен"]]
    for invoice in billing.list_invoice_rows(period_from=params.get("from"),
                                             period_to=params.get("to")):
        label = labels.get(invoice["property_id"], f"#{invoice['property_id']}")
        for line in invoice["lines"]:
            invoice_rows.append([
                label, invoice["period"], line["label"],
                line["quantity"] or "", line["rate"], line["amount"],
                invoice["total"],
                invoice["issued_at"] or "черновик"])
    invoice_rows.append(["Итого", "", "", "", "",
                         xlsx.Formula(f"SUM(F2:F{len(invoice_rows)})"), "", ""])

    payment_rows = [["Объект", "Период счёта", "Источник", "Сумма", "Получен"]]
    for payment in payments.list_confirmed_payments(
            period_from=params.get("from"), period_to=params.get("to")):
        payment_rows.append([
            labels.get(payment["property_id"], f"#{payment['property_id']}"),
            payment["period"], payment["source"], payment["amount"],
            payment["submitted_at"]])
    payment_rows.append(["Итого", "", "",
                         xlsx.Formula(f"SUM(D2:D{len(payment_rows)})"), ""])

    payload = xlsx.workbook(stamp, [("Начисления", invoice_rows),
                                    ("Платежи", payment_rows)])
    return f"financial_{stamp:%Y%m%d_%H%M}.xlsx", payload
