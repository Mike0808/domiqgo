"""Учётные записи и доступ: пункты №31 и №33 гап-анализа.

| Пункт | Что зафиксировано                                     | Кто перепишет |
|-------|-------------------------------------------------------|---------------|
| №31   | ~~на одну квартиру можно завести нескольких жильцов~~ → сторона договора одна, остальные приостановлены | **исправлен D3** |
| №33   | ~~владелец не может подключить себе OAuth~~ → согласие принадлежит учётной записи, владелец подключает провайдера сам | **исправлен C4b** |

№33 был тестом на дефект: он закреплял поломку, а не правило. C4a перенёс
согласие с жильца на учётную запись, C4b убрал проверку профиля жильца из
адаптера и с экрана подключений — оба теста переписаны на рабочий сценарий
тем же коммитом.
"""

from datetime import date
from decimal import Decimal

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.utils import timezone

from billing.adapters import NoSignupSocialAccountAdapter
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, MonthlyStatement, Tenant
from billing.tests.tenancies import draft
from modules.identity import api as identity

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]


class _FakeSocialLogin:
    """Ровно тот атрибут, который читает адаптер (как в test_oauth_adapter)."""

    def __init__(self, is_existing):
        self.is_existing = is_existing


def _request(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


def _login(username):
    client = Client()
    assert client.login(username=username, password="pass12345")
    return client


# --------------------------------------------------------------------------
# №31 — сторона договора одна. Исправлен шагом D3 (ADR-0011).
# --------------------------------------------------------------------------

def test_after_the_choice_only_the_party_keeps_the_cabinet():
    """До D3 оба супруга видели один счёт; после выбора стороны кабинет
    остаётся у стороны договора, вторая запись приостановлена — обратимо,
    без удаления данных."""
    from modules.identity import api as identity
    from modules.tenancy import api as tenancy_api

    apartment = Apartment.objects.create(label="кв")
    users = {}
    for username in ("ivanov", "ivanova"):
        user = User.objects.create_user(username, password="pass12345")
        Tenant.objects.create(user=user, apartment=apartment)
        users[username] = user
        draft(apartment, user.pk)
    invoice = MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), total=Decimal("1000.00"))

    chosen = tenancy_api.active_tenancy_for_account(users["ivanov"].pk, date(2026, 5, 1))
    tenancy_api.correct_tenancy(chosen.tenancy_id, started_on=chosen.started_on)
    identity.suspend_account(users["ivanova"].pk, timezone.now())

    response = _login("ivanov").get("/history/")
    assert list(response.context["statements"]) == [invoice]

    blocked = Client()
    assert not blocked.login(username="ivanova", password="pass12345")

    identity.restore_account(users["ivanova"].pk)   # решение обратимо
    assert Client().login(username="ivanova", password="pass12345")


# --------------------------------------------------------------------------
# №33 — владелец подключает провайдера сам. Исправлен шагом C4b.
# --------------------------------------------------------------------------

def test_owner_without_consent_is_sent_to_the_consent_screen():
    """Половина правила: без согласия провайдера не привязать никому.

    Владелец, как и жилец, отправляется на экран подключений — но уже не
    потому, что у него нет профиля жильца, а потому, что согласия нет в
    журнале учётной записи.
    """
    owner = User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    adapter = NoSignupSocialAccountAdapter()

    with pytest.raises(ImmediateHttpResponse) as raised:
        adapter.pre_social_login(_request(owner), _FakeSocialLogin(is_existing=False))

    assert raised.value.response.status_code == 302
    assert raised.value.response.headers["Location"] == "/connections/"


def test_consent_screen_opens_for_the_owner_and_records_consent():
    """Вторая половина: экран подключений открывается для любой учётной
    записи, а не только для жильца. Круг разомкнут — владелец даёт согласие
    и после этого адаптер пропускает привязку провайдера.
    """
    owner = User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    client = _login("boss")

    screen = client.get("/connections/")
    assert screen.status_code == 200
    assert "form" in screen.context  # экран согласия, не редирект в админку

    assert client.post("/connections/", {"consent": "on"}).status_code == 302
    assert identity.has_current_consent(owner.pk, PRIVACY_POLICY_VERSION)

    adapter = NoSignupSocialAccountAdapter()
    adapter.pre_social_login(_request(owner), _FakeSocialLogin(is_existing=False))
