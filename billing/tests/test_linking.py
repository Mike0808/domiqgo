from django.contrib.auth.models import User
import pytest
from billing.models import Apartment, Tenant
from billing.services.linking import (
    generate_link_code, link_chat, InvalidLinkCodeError,
)

pytestmark = pytest.mark.django_db

def _tenant(username="t"):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user(username, password="x")
    return Tenant.objects.create(user=u, apartment=a, full_name="Т")

def test_generate_code_is_non_empty_and_saved():
    t = _tenant()
    code = generate_link_code(t)
    assert code
    t.refresh_from_db()
    assert t.link_code == code

def test_link_binds_chat_and_is_single_use():
    t = _tenant()
    code = generate_link_code(t)
    linked = link_chat("telegram", 12345, code)
    assert linked.pk == t.pk
    t.refresh_from_db()
    assert t.messenger_platform == "telegram"
    assert t.messenger_chat_id == "12345"
    assert t.link_code == ""                      # consumed
    with pytest.raises(InvalidLinkCodeError):     # cannot reuse
        link_chat("telegram", 999, code)

def test_empty_code_rejected_and_matches_nobody():
    _tenant("a")   # has blank link_code by default
    with pytest.raises(InvalidLinkCodeError):
        link_chat("telegram", 1, "")

def test_unknown_code_rejected():
    with pytest.raises(InvalidLinkCodeError):
        link_chat("telegram", 1, "does-not-exist")
