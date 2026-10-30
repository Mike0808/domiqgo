"""Заявленные платежи — чужое знание, внедрённое интерфейсом (шаг H3).

«На проверке» — состояние платежа, то есть знание Payments; а спрашивать
Payments модуль Billing не вправе: стрелка зависимостей идёт payments →
billing (ADR-0014, ADR-0015), обратной нет. Провайдер внедряется интерфейсным
слоем — тот же приём, что резолвер владельцев в F3 и метаданные документов
в G2.

Непривязанный провайдер отвечает «нет»: без интерфейса модуль честно не
знает о заявленных чеках, и статус счёта колеблется только между «не
оплачено» и «оплачено» — тем, что выводится из его собственной сверки.
"""


def _nobody_claims(invoice_id) -> bool:
    return False


_has_pending_claim = _nobody_claims


def wire(has_pending_claim) -> None:
    global _has_pending_claim
    _has_pending_claim = has_pending_claim


def has_pending_claim(invoice_id) -> bool:
    return _has_pending_claim(invoice_id)
