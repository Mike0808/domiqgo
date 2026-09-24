from datetime import date
from django.core.files.base import ContentFile
import pytest
from billing.models import Apartment, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

@pytest.fixture
def media_isolation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

def _stmt():
    a = Apartment.objects.create(label="кв. 1")
    return MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

def test_payment_defaults_to_pending(media_isolation):
    stmt = _stmt()
    p = Payment(statement_id=stmt.pk, source=Payment.TELEGRAM)
    p.file.save("r.jpg", ContentFile(b"img"), save=True)
    assert p.status == Payment.PENDING
    assert Payment.objects.filter(statement_id=stmt.pk).count() == 1

def test_payment_source_choices_cover_all_channels():
    codes = {c for c, _ in Payment.SOURCE_CHOICES}
    # MANUAL появился на E1: ручная отметка владельца, без чека.
    assert codes == {Payment.TELEGRAM, Payment.MAX, Payment.WEB, Payment.MANUAL}
