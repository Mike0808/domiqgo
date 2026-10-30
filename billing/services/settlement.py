"""Интерфейсная оболочка сверки (шаг H3).

Проекция, её пересборка и подписка на платёжные события переехали в
`modules/billing/application` (ADR-0015); здесь — реэкспорт для старых
импортов админки и тестов.
"""

from modules.billing.api import (  # noqa: F401 — реэкспорт для старых импортов
    rebuild_settlement, settlement_matches_journal,
)
