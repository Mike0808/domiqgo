"""Код привязки — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища.
"""

import pytest

from modules.identity.domain import InvalidLinkCode, LinkCode, presented


def test_an_issued_code_is_not_empty_and_belongs_to_the_account():
    link_code = LinkCode.issue(7)

    assert link_code.account_id == 7
    assert link_code.code


def test_two_issues_give_different_codes():
    assert LinkCode.issue(7).code != LinkCode.issue(7).code


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_a_blank_code_is_rejected_before_any_lookup(raw):
    """У записи без кода «пустой код» не должен совпасть ни с чем — и не
    должен даже искаться."""
    with pytest.raises(InvalidLinkCode):
        presented(raw)


def test_a_presented_code_is_stripped():
    assert presented("  abc  ") == "abc"
