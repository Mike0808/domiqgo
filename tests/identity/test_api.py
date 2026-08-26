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
