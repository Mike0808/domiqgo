"""Панель владельца: заселение и выезд идут командами модуля."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from modules.properties import api as properties
from modules.tenancy import api

pytestmark = pytest.mark.django_db


@pytest.fixture
def flat():
    return properties.register_property("кв", has_hot_water=False)


def _add(admin_client, flat, account_id=7, started="2026-03-01", rent="30000"):
    return admin_client.post("/admin/tenancy/tenancy/add/", {
        "property_id": str(flat), "account_id": str(account_id),
        "full_name": "Иванов", "started_on": started,
        "rent": rent, "internet": "0", "other_fixed": "0",
    })


def test_adding_from_the_panel_starts_a_tenancy(admin_client, flat):
    resp = _add(admin_client, flat)

    assert resp.status_code == 302
    contract = api.tenancy_for(flat, date(2026, 4, 1))
    assert contract.account_id == 7 and contract.terms.rent == Decimal("30000")
    assert contract.start_confirmed        # заведён владельцем, не миграцией


def test_an_overlap_is_a_form_error_not_a_500(admin_client, flat):
    _add(admin_client, flat)

    resp = _add(admin_client, flat, account_id=8, started="2026-05-01")

    assert resp.status_code == 200         # форма вернулась с ошибкой
    assert api.tenancy_for(flat, date(2026, 5, 1)).account_id == 7


def test_setting_the_move_out_date_ends_the_tenancy(admin_client, flat):
    _add(admin_client, flat)
    contract = api.tenancy_for(flat, date(2026, 4, 1))

    resp = admin_client.post(
        f"/admin/tenancy/tenancy/{contract.tenancy_id}/change/",
        {"ended_on": "2026-06-30"})

    assert resp.status_code == 302
    assert api.get_tenancy(contract.tenancy_id).ended_on == date(2026, 6, 30)
    assert api.tenancy_for(flat, date(2026, 7, 1)) is None


def test_moving_out_before_moving_in_is_a_form_error(admin_client, flat):
    _add(admin_client, flat)
    contract = api.tenancy_for(flat, date(2026, 4, 1))

    resp = admin_client.post(
        f"/admin/tenancy/tenancy/{contract.tenancy_id}/change/",
        {"ended_on": "2026-01-01"})

    assert resp.status_code == 200
    assert api.get_tenancy(contract.tenancy_id).is_open


def test_the_terms_of_an_existing_tenancy_are_not_editable(admin_client, flat):
    """Инвариант 3: правится только дата выезда; условия — новый договор."""
    _add(admin_client, flat)
    contract = api.tenancy_for(flat, date(2026, 4, 1))

    admin_client.post(
        f"/admin/tenancy/tenancy/{contract.tenancy_id}/change/",
        {"rent": "999999", "ended_on": ""})

    assert api.get_tenancy(contract.tenancy_id).terms.rent == Decimal("30000")
