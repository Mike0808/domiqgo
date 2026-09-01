"""Учётные записи и доступ: пункты №31 и №33 гап-анализа.

| Пункт | Что зафиксировано                                     | Кто перепишет |
|-------|-------------------------------------------------------|---------------|
| №31   | на одну квартиру можно завести нескольких жильцов      | D3            |
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

from billing.adapters import NoSignupSocialAccountAdapter
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, MonthlyStatement, Tenant
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
# №31 — несколько жильцов на квартиру. Переписывает шаг D3.
# --------------------------------------------------------------------------

def test_two_tenants_of_one_apartment_each_have_their_own_access():
    """`related_name="tenants"` допускает двоих, и оба видят один и тот же счёт.

    После D3 (ADR-0011) стороной договора становится одна учётная запись;
    вторая приостанавливается, **и в установке, где супруги входят по
    отдельности, второй потеряет доступ к кабинету**.
    """
    apartment = Apartment.objects.create(label="кв")
    for username in ("ivanov", "ivanova"):
        user = User.objects.create_user(username, password="pass12345")
        Tenant.objects.create(user=user, apartment=apartment)
    invoice = MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), total=Decimal("1000.00"))

    assert apartment.tenants.count() == 2
    for username in ("ivanov", "ivanova"):
        response = _login(username).get("/history/")
        assert list(response.context["statements"]) == [invoice]


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
