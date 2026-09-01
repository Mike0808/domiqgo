"""Договор аренды: объект, жилец, период проживания, условия.

Договор — факт «здесь живёт такой-то с такого-то числа на таких-то условиях»,
не обязательно бумага. Условия внутри договора неизменны (инвариант 3): их
изменение — это новый договор, и история условий получается даром.

Здесь только stdlib. Ни Django, ни базы.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal


class EndBeforeStart(ValueError):
    """Дата выезда раньше даты заселения (инвариант 2)."""


class AlreadyEnded(ValueError):
    """У договора уже есть дата выезда."""


@dataclass(frozen=True)
class Terms:
    """Денежные условия: арендная плата, интернет, прочие постоянные платежи.

    Неизменяемы по построению — так инвариант 3 держится типом, а не
    проверкой.
    """

    rent: Decimal = Decimal("0")
    internet: Decimal = Decimal("0")
    other_fixed: Decimal = Decimal("0")


@dataclass(frozen=True)
class Tenancy:
    """Один договор. Корень агрегата вместе с историей объекта (`history.py`).

    `started_on` есть всегда: без даты договор не может ответить ни «действует
    ли», ни «чей это период». Но дата может быть **неподтверждённой** — такие
    договоры создала миграция из записей жильцов, у которых дат не было вовсе;
    владелец подтверждает или исправляет её в диалоге шага D2. Пока она не
    подтверждена, система работает, а договор помечен требующим внимания.
    """

    tenancy_id: int | None
    property_id: int
    account_id: int
    full_name: str
    started_on: date
    terms: Terms
    ended_on: date | None = None
    start_confirmed: bool = True

    def __post_init__(self):
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise EndBeforeStart(
                f"выезд {self.ended_on:%d.%m.%Y} раньше заселения "
                f"{self.started_on:%d.%m.%Y}")

    def covers(self, day: date) -> bool:
        """Входит ли день в период проживания — по дату выезда включительно."""
        return self.started_on <= day and (self.ended_on is None or day <= self.ended_on)

    def is_active_on(self, day: date) -> bool:
        return self.covers(day)

    @property
    def is_open(self) -> bool:
        """Без даты выезда — договор действующий."""
        return self.ended_on is None

    def end(self, on: date) -> "Tenancy":
        """Зафиксировать выезд. Дата — свершившийся факт; спрашивать Billing,
        выставлены ли счета до неё, модуль не вправе (цикл)."""
        if self.ended_on is not None:
            raise AlreadyEnded(f"договор уже завершён {self.ended_on:%d.%m.%Y}")
        return replace(self, ended_on=on)

    def overlaps(self, other: "Tenancy") -> bool:
        """Пересекаются ли периоды хотя бы одним днём."""
        return self.started_on <= _end_or_forever(other) and other.started_on <= _end_or_forever(self)


def _end_or_forever(tenancy: Tenancy) -> date:
    return tenancy.ended_on if tenancy.ended_on is not None else date.max
