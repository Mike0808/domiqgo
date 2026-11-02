import pytest
from django.contrib.auth.models import User
from django.test import Client
from billing.models import Apartment, Tenant

pytestmark = pytest.mark.django_db

def test_login_page_footer_shows_build_version(settings):
    settings.APP_VERSION = "4d57249 2026-11-02"
    html = Client().get("/login/").content.decode()
    assert "версия 4d57249 2026-11-02" in html

def test_portal_footer_shows_build_version(settings):
    settings.APP_VERSION = "abc1234 2026-12-01"
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="pass12345")
    Tenant.objects.create(user=u, apartment=a)
    c = Client()
    assert c.login(username="t", password="pass12345")
    assert "версия abc1234 2026-12-01" in c.get("/receipts/").content.decode()

def test_version_defaults_to_unknown(settings, monkeypatch):
    # An image built without APP_VERSION must say so, not show a stale value.
    monkeypatch.delenv("APP_VERSION", raising=False)
    import importlib, config.settings as s
    assert importlib.reload(s).APP_VERSION == "неизвестна"
