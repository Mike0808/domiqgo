import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

def test_privacy_policy_reachable_without_login():
    resp = Client().get("/privacy/")
    assert resp.status_code == 200
    html = resp.content.decode()
    for phrase in ("Оператор", "Яндекс", "VK", "Госуслуги", "согласие",
                   "срок хранения", "Роскомнадзор"):
        assert phrase in html, f"missing: {phrase}"
