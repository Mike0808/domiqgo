import os
import subprocess
import sys
import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

def test_socialaccount_connections_url_redirects_anonymous_to_login():
    # Proves allauth.socialaccount.urls is wired in and login-gated.
    resp = Client().get("/accounts/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_login_page_shows_all_three_provider_buttons():
    resp = Client().get("/login/")
    html = resp.content.decode()
    assert "Яндекс" in html
    assert "VK" in html
    assert "Госуслуги" in html

def test_yandex_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/yandex/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404

def test_vk_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/vk/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404

def test_esia_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/esia/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404


# --- ESIA production fail-closed check -------------------------------------
#
# billing/esia_provider/views.py decodes the ESIA id_token WITHOUT verifying
# its cryptographic signature (documented, deliberate limitation). config/
# settings.py must refuse to boot with DEBUG=0 against a non-sandbox
# ESIA_BASE_URL unless ESIA_ALLOW_UNVERIFIED_SIGNATURE=1 is explicitly set.
# Settings are evaluated at *import* time, so — like there is no way to
# flip DEBUG/SECRET_KEY on the already-imported config.settings module used
# by this test process — the check has to run in a fresh subprocess.

def _run_settings_import(extra_env):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **extra_env}
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env, capture_output=True, text=True,
    )

def test_esia_production_base_url_without_override_fails_closed():
    result = _run_settings_import({
        "DEBUG": "0",
        "SECRET_KEY": "x" * 50,
        "ESIA_BASE_URL": "https://esia.gosuslugi.ru",
    })
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "ESIA_BASE_URL points at production Gosuslugi" in result.stderr

def test_esia_production_base_url_with_explicit_override_boots():
    result = _run_settings_import({
        "DEBUG": "0",
        "SECRET_KEY": "x" * 50,
        "ESIA_BASE_URL": "https://esia.gosuslugi.ru",
        "ESIA_ALLOW_UNVERIFIED_SIGNATURE": "1",
    })
    assert result.returncode == 0, result.stderr

def test_esia_sandbox_base_url_in_production_boots_without_override():
    result = _run_settings_import({
        "DEBUG": "0",
        "SECRET_KEY": "x" * 50,
        "ESIA_BASE_URL": "https://esia-portal1.test.gosuslugi.ru",
    })
    assert result.returncode == 0, result.stderr
