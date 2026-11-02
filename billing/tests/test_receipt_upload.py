from datetime import date
import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from billing.models import Apartment, Tenant, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

@pytest.fixture
def receipt_setup(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("ivanov", password="pass12345")
    tenant = Tenant.objects.create(user=u, apartment=a, full_name="Иванов")
    return tenant, a

def _login(username):
    c = Client()
    assert c.login(username=username, password="pass12345")
    return c

def _jpg(name="check.jpg", data=b"\xff\xd8img"):
    return SimpleUploadedFile(name, data, content_type="image/jpeg")

def test_receipts_page_requires_login():
    resp = Client().get("/receipts/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_user_without_tenant_gets_friendly_page(receipt_setup):
    User.objects.create_user("nobody", password="pass12345")
    resp = _login("nobody").get("/receipts/")
    assert resp.status_code == 200
    assert "billing/no_tenant.html" in [t.name for t in resp.templates]

def test_upload_attaches_to_earliest_unpaid_with_web_source(receipt_setup):
    tenant, a = receipt_setup
    june = MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1))
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))
    resp = _login("ivanov").post("/receipts/", {"file": _jpg()})
    assert resp.status_code == 302
    payment = Payment.objects.get()
    assert payment.statement == june
    assert payment.source == Payment.WEB
    assert payment.file.read() == b"\xff\xd8img"
    june.refresh_from_db()
    assert june.status == MonthlyStatement.PENDING

def test_upload_without_unpaid_statement_shows_error(receipt_setup):
    _, a = receipt_setup
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="paid")
    resp = _login("ivanov").post("/receipts/", {"file": _jpg()}, follow=True)
    assert not Payment.objects.exists()
    assert "Нет неоплаченных начислений" in resp.content.decode()

def test_page_hides_upload_form_when_nothing_unpaid(receipt_setup):
    _, a = receipt_setup
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="paid")
    resp = _login("ivanov").get("/receipts/")
    assert resp.context["form"] is None

def test_rejects_disallowed_extension(receipt_setup):
    _, a = receipt_setup
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1))
    resp = _login("ivanov").post(
        "/receipts/", {"file": SimpleUploadedFile("evil.html", b"<script>", "text/html")})
    assert resp.status_code == 200
    assert resp.context["form"].errors["file"]
    assert not Payment.objects.exists()

def test_rejects_oversized_file(receipt_setup, settings):
    _, a = receipt_setup
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1))
    big = _jpg(data=b"x" * (10 * 1024 * 1024 + 1))
    resp = _login("ivanov").post("/receipts/", {"file": big})
    assert resp.status_code == 200
    assert resp.context["form"].errors["file"]
    assert not Payment.objects.exists()

def test_lists_only_own_apartments_receipts(receipt_setup):
    tenant, a = receipt_setup
    mine = MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1))
    Payment.objects.create(statement=mine, source=Payment.TELEGRAM,
                           file=ContentFile(b"1", name="mine.jpg"))
    other_apt = Apartment.objects.create(label="чужая")
    theirs = MonthlyStatement.objects.create(apartment=other_apt, period=date(2026, 6, 1))
    Payment.objects.create(statement=theirs, source=Payment.WEB,
                           file=ContentFile(b"2", name="theirs.jpg"))
    resp = _login("ivanov").get("/receipts/")
    assert [p.statement for p in resp.context["payments"]] == [mine]

def test_tenant_can_open_own_receipt_but_not_foreign(receipt_setup):
    tenant, a = receipt_setup
    mine = MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1))
    own = Payment.objects.create(statement=mine, source=Payment.WEB,
                                 file=ContentFile(b"own", name="own.jpg"))
    other_apt = Apartment.objects.create(label="чужая")
    theirs = MonthlyStatement.objects.create(apartment=other_apt, period=date(2026, 6, 1))
    foreign = Payment.objects.create(statement=theirs, source=Payment.WEB,
                                     file=ContentFile(b"foreign", name="foreign.jpg"))
    c = _login("ivanov")
    resp = c.get(own.file.url)
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == b"own"
    assert c.get(foreign.file.url).status_code == 404
