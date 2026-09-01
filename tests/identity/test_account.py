"""Тип учётной записи — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища.
"""

from modules.identity.domain import Account, AccountType, type_from_staff_flag


def test_staff_flag_means_owner():
    assert type_from_staff_flag(True) is AccountType.OWNER


def test_no_staff_flag_means_tenant():
    assert type_from_staff_flag(False) is AccountType.TENANT


def test_only_an_owner_account_is_owner():
    assert Account(1, AccountType.OWNER).is_owner is True
    assert Account(1, AccountType.TENANT).is_owner is False
