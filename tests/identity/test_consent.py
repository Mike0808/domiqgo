"""Журнал согласий — правила без базы.

Ни одного `django_db`: домен обязан проверяться без хранилища.
"""

from datetime import datetime, timedelta

import pytest

from modules.identity.domain import Consent, ConsentJournal

JULY = datetime(2026, 7, 27, 12, 0)
OLD = "2025-01-01"
CURRENT = "2026-07-27"


def _journal(*entries):
    return ConsentJournal(1, [Consent(version, at) for version, at in entries])


def test_an_empty_journal_covers_nothing():
    assert _journal().covers(CURRENT) is False


def test_a_journal_covers_the_version_it_holds():
    assert _journal((CURRENT, JULY)).covers(CURRENT) is True


def test_an_older_consent_does_not_cover_the_new_text():
    """Текст политики изменился — прежнее согласие относится к прежнему
    тексту. Иначе оператор считал бы согласованным то, чего человек не видел."""
    assert _journal((OLD, JULY)).covers(CURRENT) is False


def test_a_newer_consent_does_not_cover_an_older_version_either():
    """Ищется точное совпадение редакции, а не «последнее согласие вообще»."""
    assert _journal((CURRENT, JULY)).covers(OLD) is False


def test_granting_records_the_version_and_the_moment():
    journal = _journal()

    consent = journal.grant(CURRENT, JULY)

    assert (consent.policy_version, consent.given_at) == (CURRENT, JULY)
    assert journal.covers(CURRENT) is True


def test_granting_keeps_the_previous_entries():
    """Инвариант 6: согласие не перезаписывается. Прежние записи — это
    доказательства согласия на прежние редакции, и терять их нельзя."""
    journal = _journal((OLD, JULY))

    journal.grant(CURRENT, JULY + timedelta(days=1))

    assert [c.policy_version for c in journal.entries] == [OLD, CURRENT]


def test_granting_the_same_version_twice_records_both():
    """Каждый акт согласия — отдельный факт. Решать за человека, что второй
    раз он согласия не давал, оператор не вправе."""
    journal = _journal()

    journal.grant(CURRENT, JULY)
    journal.grant(CURRENT, JULY + timedelta(days=1))

    assert len(journal.entries) == 2


def test_entries_are_ordered_by_moment():
    """Порядок появления, а не порядок вставки: история читается сверху вниз."""
    journal = _journal((CURRENT, JULY), (OLD, JULY - timedelta(days=365)))

    assert [c.policy_version for c in journal.entries] == [OLD, CURRENT]


def test_the_journal_does_not_expose_its_list():
    journal = _journal((CURRENT, JULY))

    journal.entries.clear()

    assert len(journal.entries) == 1


def test_a_consent_is_immutable():
    consent = _journal((CURRENT, JULY)).entries[0]

    with pytest.raises(Exception):
        consent.policy_version = OLD
