import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from billing.models import Apartment, Tenant, Document

pytestmark = pytest.mark.django_db

@pytest.fixture
def media_setup(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("owner", password="pass12345")
    t = Tenant.objects.create(user=u, apartment=a, full_name="Владелец")
    doc = Document.objects.create(
        tenant=t,
        file=SimpleUploadedFile("contract.pdf", b"%PDF-1.4 test"),
        title="Договор аренды")
    return u, doc

def test_anonymous_media_request_redirects_to_login(media_setup):
    _, doc = media_setup
    resp = Client().get(doc.file.url)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_owner_can_download_own_document(media_setup):
    _, doc = media_setup
    c = Client()
    assert c.login(username="owner", password="pass12345")
    resp = c.get(doc.file.url)
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == b"%PDF-1.4 test"

def test_other_tenant_gets_404_for_foreign_document(media_setup):
    _, doc = media_setup
    a2 = Apartment.objects.create(label="чужая кв")
    u2 = User.objects.create_user("other", password="pass12345")
    Tenant.objects.create(user=u2, apartment=a2, full_name="Чужой")
    c = Client()
    assert c.login(username="other", password="pass12345")
    assert c.get(doc.file.url).status_code == 404

def test_staff_can_download_any_document(media_setup):
    _, doc = media_setup
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    c = Client()
    assert c.login(username="boss", password="pass12345")
    assert c.get(doc.file.url).status_code == 200
