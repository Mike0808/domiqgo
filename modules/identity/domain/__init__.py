"""Доменный слой: правила и инварианты.

Не импортирует django, requests, allauth и прочие фреймворки — только stdlib.

Здесь журнал согласий (инвариант 6) и код привязки (инвариант 5). Правила
входа — «внешний провайдер не создаёт учётную запись», «привязка требует
действующего согласия» — сегодня живут в адаптере allauth и настройке
фреймворка; они переезжают сюда шагом **C4d**.
"""

from .consent import Consent, ConsentJournal
from .link_code import InvalidLinkCode, LinkCode, presented

__all__ = ["Consent", "ConsentJournal", "InvalidLinkCode", "LinkCode", "presented"]
