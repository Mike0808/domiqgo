"""Журнал согласий на обработку персональных данных.

Согласие — не признак, а **факт во времени**: дано тогда-то, на такую-то
редакцию политики. Для 152-ФЗ доказательством служит именно это сочетание, и
храня лишь последнее согласие, оператор теряет возможность подтвердить
прежнее — ровно тогда, когда это понадобится.

Здесь только stdlib. Ни Django, ни базы.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Consent:
    """Один акт согласия."""

    policy_version: str
    given_at: datetime


class ConsentJournal:
    """Все согласия одной учётной записи, в порядке появления.

    Корень — журнал, а не отдельное согласие: инвариант 6 («согласие не
    перезаписывается») охватывает всю историю сразу, и держать его может
    только объект, который её видит.
    """

    def __init__(self, account_id: int, entries=()):
        self.account_id = account_id
        self._entries: list[Consent] = sorted(entries, key=lambda c: c.given_at)

    @property
    def entries(self) -> list[Consent]:
        """Копия: журнал не правят снаружи."""
        return list(self._entries)

    def covers(self, policy_version: str) -> bool:
        """Есть ли согласие на эту редакцию политики.

        Ищется точное совпадение редакции, а не «последнее согласие вообще»:
        текст политики изменился — прежнее согласие относится к прежнему
        тексту и новую редакцию не покрывает.
        """
        return any(c.policy_version == policy_version for c in self._entries)

    def grant(self, policy_version: str, at: datetime) -> Consent:
        """Зафиксировать согласие.

        Всегда добавляет запись, даже если согласие на эту редакцию уже есть:
        каждый акт согласия — отдельный факт, и решать за пользователя, что
        второй раз он согласия не давал, оператор не вправе. Прежние записи
        не трогаются никогда — в этом весь смысл журнала.
        """
        consent = Consent(policy_version=policy_version, given_at=at)
        self._entries.append(consent)
        self._entries.sort(key=lambda c: c.given_at)
        return consent
