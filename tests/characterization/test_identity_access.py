"""Учётные записи и доступ: пункты №31 и №33 гап-анализа.

| Пункт | Что зафиксировано                                     | Кто перепишет |
|-------|-------------------------------------------------------|---------------|
| №31   | на одну квартиру можно завести нескольких жильцов      | D3            |
| №33   | владелец не может подключить себе OAuth — ходит по кругу | C4          |

№33 — тест на дефект: он закрепляет поломку, а не правило. Чинится тем же
шагом, который переносит согласие с жильца на учётную запись; если C4
откладывается, дефект чинится отдельно и раньше.
"""

from datetime import date
from decimal import Decimal

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth.models import User
from django.test import Client, RequestFactory

from billing.adapters import NoSignupSocialAccountAdapter
from billing.models import Apartment, MonthlyStatement, Tenant

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
        Tenant.objects.create(user=user, apartment=apartment, full_name=username)
    invoice = MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), total=Decimal("1000.00"))

    assert apartment.tenants.count() == 2
    for username in ("ivanov", "ivanova"):
        response = _login(username).get("/history/")
        assert list(response.context["statements"]) == [invoice]


# --------------------------------------------------------------------------
# №33 — круг, из которого владельцу не выйти. Переписывает шаг C4.
# --------------------------------------------------------------------------

def test_owner_attaching_a_provider_is_sent_to_the_consent_screen():
    """Первая половина круга: согласие ищется через профиль жильца.

    У владельца профиля жильца нет, поэтому адаптер считает согласие
    отсутствующим и отправляет его на экран подключений.
    """
    owner = User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    adapter = NoSignupSocialAccountAdapter()

    with pytest.raises(ImmediateHttpResponse) as raised:
        adapter.pre_social_login(_request(owner), _FakeSocialLogin(is_existing=False))

    assert raised.value.response.status_code == 302
    assert raised.value.response.headers["Location"] == "/connections/"


def test_consent_screen_bounces_the_owner_to_the_admin():
    """Вторая половина круга: экран подключений для пользователя без профиля
    жильца немедленно уходит в админку — дать согласие негде.

    Вместе с предыдущим тестом это замкнутый круг: подключить провайдера
    владелец не может никаким путём. После C4 согласие принадлежит учётной
    записи, экран открывается, и оба теста переписываются на рабочий сценарий.
    """
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")

    response = _login("boss").get("/connections/")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/")
