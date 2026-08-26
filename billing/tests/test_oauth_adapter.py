from datetime import date
import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory
from billing.adapters import NoSignupSocialAccountAdapter
from django.utils import timezone

from modules.identity import api as identity
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Tenant

pytestmark = pytest.mark.django_db

class _FakeSocialLogin:
    """Stand-in exposing only the attribute the adapter actually reads —
    avoids depending on allauth's real SocialLogin constructor shape."""
    def __init__(self, is_existing):
        self.is_existing = is_existing

def _request(user):
    req = RequestFactory().get("/")
    req.user = user
    return req

def test_is_open_for_signup_is_always_false():
    adapter = NoSignupSocialAccountAdapter()
    assert adapter.is_open_for_signup(_request(AnonymousUser()), _FakeSocialLogin(False)) is False

def test_pre_social_login_proceeds_for_existing_link():
    adapter = NoSignupSocialAccountAdapter()
    # Must not raise for an already-linked account (normal login).
    adapter.pre_social_login(_request(AnonymousUser()), _FakeSocialLogin(True))

def test_pre_social_login_rejects_anonymous_unlinked():
    from allauth.core.exceptions import ImmediateHttpResponse
    adapter = NoSignupSocialAccountAdapter()
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request(AnonymousUser()), _FakeSocialLogin(False))

def test_pre_social_login_redirects_to_connections_when_consent_missing():
    from allauth.core.exceptions import ImmediateHttpResponse
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("ivanov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Иванов")  # no consent given
    adapter = NoSignupSocialAccountAdapter()
    with pytest.raises(ImmediateHttpResponse) as exc:
        adapter.pre_social_login(_request(u), _FakeSocialLogin(False))
    assert exc.value.response.status_code == 302
    assert exc.value.response.headers["Location"] == "/connections/"

def test_pre_social_login_proceeds_when_consent_given():
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("petrov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Петров")
    identity.grant_privacy_consent(u.pk, PRIVACY_POLICY_VERSION, timezone.now())
    adapter = NoSignupSocialAccountAdapter()
    # Must not raise — connect is allowed once consent matches the current version.
    adapter.pre_social_login(_request(u), _FakeSocialLogin(False))
