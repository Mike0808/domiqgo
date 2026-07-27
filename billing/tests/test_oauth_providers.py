import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

def test_socialaccount_connections_url_redirects_anonymous_to_login():
    # Proves allauth.socialaccount.urls is wired in and login-gated.
    resp = Client().get("/accounts/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
