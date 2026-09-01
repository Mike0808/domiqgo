"""Правила входа через внешнего провайдера (инварианты 1 и 2).

Внешняя личность — учётная запись у Яндекса, VK, Госуслуг. Придя с ней,
человек попадает в одну из четырёх ситуаций, и решает их домен, а не
настройка фреймворка: настройка молча перестаёт действовать при смене
библиотеки аутентификации, правило домена — нет.

Здесь только stdlib. Ни Django, ни allauth.
"""

from enum import Enum


class ExternalLoginDecision(Enum):
    SIGN_IN = "sign_in"
    """Личность уже привязана к записи — обычный вход."""

    LINK = "link"
    """Личность новая, человек вошёл по паролю и дал согласие — привязать."""

    CONSENT_REQUIRED = "consent_required"
    """Личность новая, человек вошёл, но согласия на текущую редакцию нет
    (инвариант 2)."""

    REJECTED = "rejected"
    """Личность новая и никто не вошёл. Записи не создаются входом через
    провайдера — их заводит владелец (инвариант 1)."""


def admit_external_login(identity_known: bool, account_present: bool,
                         consent_covers_policy: bool) -> ExternalLoginDecision:
    """Что делать с пришедшей внешней личностью.

    Порядок проверок и есть правило: известную личность пускают без вопросов
    о согласии — оно спрашивалось при привязке; неизвестную привязывают
    только к уже вошедшему и только при согласии; без вошедшего — отказ.
    """
    if identity_known:
        return ExternalLoginDecision.SIGN_IN
    if not account_present:
        return ExternalLoginDecision.REJECTED
    if not consent_covers_policy:
        return ExternalLoginDecision.CONSENT_REQUIRED
    return ExternalLoginDecision.LINK
