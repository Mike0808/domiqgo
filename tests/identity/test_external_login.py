"""Правила входа через внешнего провайдера — без базы и без allauth.

Ни одного `django_db`: инварианты 1 и 2 обязаны проверяться как правила
домена, а не как поведение настройки фреймворка.
"""

import pytest

from modules.identity.domain import ExternalLoginDecision, admit_external_login


def test_a_known_identity_signs_in():
    """Согласие при входе не спрашивается: его спросили при привязке."""
    assert admit_external_login(
        identity_known=True, account_present=False, consent_covers_policy=False,
    ) is ExternalLoginDecision.SIGN_IN


def test_an_unknown_identity_with_nobody_signed_in_is_rejected():
    """Инвариант 1: вход через провайдера записи не создаёт."""
    assert admit_external_login(
        identity_known=False, account_present=False, consent_covers_policy=True,
    ) is ExternalLoginDecision.REJECTED


def test_linking_without_consent_asks_for_consent_first():
    """Инвариант 2: новый провайдер — только при действующем согласии."""
    assert admit_external_login(
        identity_known=False, account_present=True, consent_covers_policy=False,
    ) is ExternalLoginDecision.CONSENT_REQUIRED


def test_linking_with_consent_is_allowed():
    assert admit_external_login(
        identity_known=False, account_present=True, consent_covers_policy=True,
    ) is ExternalLoginDecision.LINK


@pytest.mark.parametrize("account_present,consent", [(True, True), (True, False)])
def test_a_known_identity_wins_over_everything_else(account_present, consent):
    """Известная личность — обычный вход, что бы ни было с текущей сессией."""
    assert admit_external_login(True, account_present, consent) is ExternalLoginDecision.SIGN_IN
