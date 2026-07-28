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
