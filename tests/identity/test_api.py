"""Публичная поверхность Identity: журнал согласий.

`transaction=True`: команда публикует событие, а шина доставляет после
фиксации.
"""

from datetime import datetime, timedelta, timezone as tz

import pytest

from bus import clear_subscribers, subscribe
from modules.identity import api
from modules.identity.events import PrivacyConsentGranted
from modules.identity.infrastructure.models import Consent

pytestmark = pytest.mark.django_db(transaction=True)

JULY = datetime(2026, 7, 27, 12, 0, tzinfo=tz.utc)
OLD = "2025-01-01"
CURRENT = "2026-07-27"
ACCOUNT = 1
OTHER = 2


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def received():
    events = []
    subscribe(PrivacyConsentGranted, events.append)
    return events


def test_a_fresh_account_has_no_consent():
    assert api.has_current_consent(ACCOUNT, CURRENT) is False


def test_granting_makes_the_consent_current(received):
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert api.has_current_consent(ACCOUNT, CURRENT) is True


def test_consent_belongs_to_the_account_not_to_everyone(received):
    """Ссылка на учётную запись — идентификатором, и путать записи нельзя:
    чужое согласие не открывает вход."""
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert api.has_current_consent(OTHER, CURRENT) is False


def test_an_old_consent_does_not_cover_the_new_policy(received):
    api.grant_privacy_consent(ACCOUNT, OLD, JULY - timedelta(days=365))

    assert api.has_current_consent(ACCOUNT, CURRENT) is False


def test_the_history_keeps_everything(received):
    """Инвариант 6: прежние согласия остаются. Для 152-ФЗ доказательством
    служит факт согласия на конкретную редакцию в конкретный момент."""
    api.grant_privacy_consent(ACCOUNT, OLD, JULY - timedelta(days=365))
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert [c.policy_version for c in api.consent_history(ACCOUNT)] == [OLD, CURRENT]


def test_a_new_consent_does_not_touch_the_old_row(received):
    api.grant_privacy_consent(ACCOUNT, OLD, JULY - timedelta(days=365))
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert Consent.objects.count() == 2


def test_the_moment_comes_from_outside(received):
    """«Сейчас» — понятие интерфейса. Перенос прежних согласий обязан сохранить
    их собственные даты, а не проставить дату переезда."""
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert api.consent_history(ACCOUNT)[0].given_at == JULY


def test_granting_announces_it(received):
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    event = received[0]
    assert isinstance(event, PrivacyConsentGranted)
    assert (event.account_id, event.policy_version) == (ACCOUNT, CURRENT)
    assert event.given_at == JULY


def test_the_event_lands_in_the_journal_of_the_bus():
    """След согласия ведётся дважды: в таблице модуля и в журнале шины. Второй
    независим от первого — таблицу можно поправить, журнал событий нет."""
    from bus.models import PublishedEvent

    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    recorded = [e.event_type.rsplit(".", 1)[-1] for e in PublishedEvent.objects.all()]
    assert recorded == ["PrivacyConsentGranted"]


def test_a_consent_crosses_the_border_without_django():
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    entry = api.consent_history(ACCOUNT)[0]

    assert not hasattr(entry, "save")


# ------------------------------------------------------------ код привязки

def test_a_redeemed_code_names_its_account():
    code = api.issue_link_code(ACCOUNT)

    assert api.redeem_link_code(code) == ACCOUNT


def test_a_code_is_single_use():
    """Инвариант 5: при погашении код перестаёт действовать."""
    code = api.issue_link_code(ACCOUNT)
    api.redeem_link_code(code)

    with pytest.raises(api.InvalidLinkCodeError):
        api.redeem_link_code(code)


def test_reissuing_retires_the_previous_code():
    """У записи один действующий код: потерянный код не должен остаться
    действующим после выпуска нового."""
    first = api.issue_link_code(ACCOUNT)
    second = api.issue_link_code(ACCOUNT)

    with pytest.raises(api.InvalidLinkCodeError):
        api.redeem_link_code(first)
    assert api.redeem_link_code(second) == ACCOUNT


def test_an_unknown_or_blank_code_is_rejected():
    for raw in ("does-not-exist", "", None):
        with pytest.raises(api.InvalidLinkCodeError):
            api.redeem_link_code(raw)


def test_a_presented_code_survives_surrounding_whitespace():
    code = api.issue_link_code(ACCOUNT)

    assert api.redeem_link_code(f"  {code} ") == ACCOUNT


# ------------------------------------------------------------ внешний вход

def _admit(identity_known, account_id):
    return api.admit_external_login(identity_known=identity_known,
                                    account_id=account_id, policy_version=CURRENT)


def test_a_signed_in_account_without_consent_is_asked_for_it():
    assert _admit(False, ACCOUNT) is api.ExternalLoginDecision.CONSENT_REQUIRED


def test_a_signed_in_account_with_consent_may_link(received):
    api.grant_privacy_consent(ACCOUNT, CURRENT, JULY)

    assert _admit(False, ACCOUNT) is api.ExternalLoginDecision.LINK


def test_someone_elses_consent_does_not_unlock_linking(received):
    api.grant_privacy_consent(OTHER, CURRENT, JULY)

    assert _admit(False, ACCOUNT) is api.ExternalLoginDecision.CONSENT_REQUIRED


def test_nobody_signed_in_with_an_unknown_identity_is_rejected():
    assert _admit(False, None) is api.ExternalLoginDecision.REJECTED


def test_a_known_identity_signs_in_regardless_of_consent():
    assert _admit(True, None) is api.ExternalLoginDecision.SIGN_IN


# ------------------------------------------------------ привязанные провайдеры

def test_a_fresh_account_has_no_linked_providers():
    assert api.list_linked_providers(ACCOUNT) == []


def test_linked_providers_are_listed_for_their_account_only():
    from allauth.socialaccount.models import SocialAccount
    from django.contrib.auth.models import User

    mine = User.objects.create_user("mine")
    theirs = User.objects.create_user("theirs")
    SocialAccount.objects.create(user=mine, provider="yandex", uid="1")
    SocialAccount.objects.create(user=mine, provider="esia", uid="2")
    SocialAccount.objects.create(user=theirs, provider="vk", uid="3")

    assert api.list_linked_providers(mine.pk) == ["esia", "yandex"]
