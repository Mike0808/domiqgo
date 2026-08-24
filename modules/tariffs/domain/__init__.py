"""Доменный слой: правила и инварианты.
Не импортирует django, requests, allauth и прочие фреймворки — только stdlib."""

from .catalogue import UTILITIES, UnknownUtility, ensure_known
from .schedule import (
    DuplicateVersion, InvalidRate, TariffSchedule, TariffVersion,
    VersionNotFound,
)

__all__ = [
    "UTILITIES", "UnknownUtility", "ensure_known",
    "TariffSchedule", "TariffVersion",
    "VersionNotFound", "DuplicateVersion", "InvalidRate",
]
