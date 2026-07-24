from datetime import date
from django.core.files.base import ContentFile
import pytest
from billing.models import Apartment, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

def _stmt():
    a = Apartment.objects.create(label="кв. 1")
    return MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

def test_payment_defaults_to_pending():
    p = Payment(statement=_stmt(), source=Payment.TELEGRAM)
    p.file.save("r.jpg", ContentFile(b"img"), save=True)
    assert p.status == Payment.PENDING
    assert p.statement.payments.count() == 1

def test_payment_source_choices_cover_all_channels():
    codes = {c for c, _ in Payment.SOURCE_CHOICES}
    assert codes == {Payment.TELEGRAM, Payment.MAX, Payment.WEB}
