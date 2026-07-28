from datetime import date
import pytest
from django.contrib.auth.models import User
from django.test import Client
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Tenant

pytestmark = pytest.mark.django_db

def _tenant(username, consented=False):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user(username, password="pass12345")
    kwargs = {}
    if consented:
        kwargs = {"privacy_consent_at": date(2026, 7, 27),
                  "privacy_consent_version": PRIVACY_POLICY_VERSION}
    Tenant.objects.create(user=u, apartment=a, full_name="Жилец", **kwargs)
    return u

def _login(username):
    c = Client()
    assert c.login(username=username, password="pass12345")
    return c

def test_connections_page_requires_login():
    resp = Client().get("/connections/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_connections_page_shows_consent_form_first(db):
    _tenant("noconsent")
    c = _login("noconsent")
    resp = c.get("/connections/")
    assert resp.status_code == 200
    assert "согласие" in resp.content.decode().lower()
    assert "Яндекс" not in resp.content.decode()  # provider list not shown yet

def test_posting_consent_records_it_and_shows_providers(db):
    _tenant("agrees")
    c = _login("agrees")
    resp = c.post("/connections/", {"consent": "on"}, follow=True)
    assert resp.status_code == 200
    tenant = Tenant.objects.get(user__username="agrees")
    assert tenant.privacy_consent_version == PRIVACY_POLICY_VERSION
    assert tenant.privacy_consent_at is not None
    assert "Яндекс" in resp.content.decode()

def test_connections_page_lists_providers_when_already_consented(db):
    _tenant("already", consented=True)
    c = _login("already")
    resp = c.get("/connections/")
    assert resp.status_code == 200
    assert "Яндекс" in resp.content.decode()
    assert "VK" in resp.content.decode()
    assert "Госуслуги" in resp.content.decode()
