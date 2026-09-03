"""Публичная поверхность Notifications: каналы доставки (шаг F1)."""

import pytest

from modules.notifications import api

pytestmark = pytest.mark.django_db

IVANOV, PETROV = 11, 12


def test_a_bound_address_resolves_to_its_account():
    api.bind_channel(IVANOV, "telegram", "555")

    assert api.resolve_account_by_channel("telegram", "555") == IVANOV
    assert api.resolve_account_by_channel("telegram", "777") is None


def test_rebinding_replaces_the_address_of_the_platform():
    """Инвариант 1: у записи один адрес на платформу — новый замещает."""
    api.bind_channel(IVANOV, "telegram", "555")
    api.bind_channel(IVANOV, "telegram", "556")

    assert api.resolve_account_by_channel("telegram", "555") is None
    assert api.resolve_account_by_channel("telegram", "556") == IVANOV
    assert len(api.list_channels(IVANOV)) == 1


def test_an_address_is_not_bound_to_two_accounts():
    """Инвариант 2: чат — не общий почтовый ящик."""
    api.bind_channel(IVANOV, "telegram", "555")

    with pytest.raises(api.AddressAlreadyBound):
        api.bind_channel(PETROV, "telegram", "555")


def test_platforms_are_independent_channels():
    api.bind_channel(IVANOV, "telegram", "555")
    api.bind_channel(IVANOV, "max", "abc")

    assert [c.platform for c in api.list_channels(IVANOV)] == ["max", "telegram"]


def test_unbinding_frees_the_address():
    api.bind_channel(IVANOV, "telegram", "555")
    api.unbind_channel(IVANOV, "telegram")

    assert api.resolve_account_by_channel("telegram", "555") is None
    api.bind_channel(PETROV, "telegram", "555")   # адрес свободен
