"""История заселений одного объекта — то, на чём держатся инварианты 1 и 5.

Непересечение периодов (инвариант 1) — свойство не одного договора, а всех
договоров объекта сразу; проверить его может только тот, кто видит их все.
То же с запретом заселять выведенный из эксплуатации объект (инвариант 5):
признак хранится здесь, полученный событием Properties, а не запросом в
момент заключения ([ADR-0009]).

Здесь только stdlib.

[ADR-0009]: ../../../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md
"""

from datetime import date

from .tenancy import Tenancy


class PeriodOverlap(ValueError):
    """У объекта уже есть договор на эти даты (инвариант 1)."""


class PropertyOutOfService(ValueError):
    """Объект выведен из эксплуатации: новые договоры не заключаются
    (инвариант 5). Действующий договор при этом не трогается."""


class PropertyHistory:
    """Все договоры одного объекта.

    Загруженная история может содержать пересечения — их оставила миграция из
    записей жильцов, где к квартире было привязано несколько человек (шаг D3
    разводит их с владельцем). Инвариант держится на **новых** договорах:
    существующее пересечение не мешает читать историю, но мешает добавить в
    неё ещё одно.
    """

    def __init__(self, property_id: int, tenancies=(), out_of_service: bool = False):
        self.property_id = property_id
        self.out_of_service = out_of_service
        self._tenancies: list[Tenancy] = sorted(
            tenancies, key=lambda t: (t.started_on, t.tenancy_id or 0))

    @property
    def tenancies(self) -> list[Tenancy]:
        return list(self._tenancies)

    def start(self, tenancy: Tenancy) -> Tenancy:
        """Заселить. Отказывает, если объект выведен или период занят."""
        if self.out_of_service:
            raise PropertyOutOfService(
                f"объект #{self.property_id} выведен из эксплуатации")
        self._ensure_free_for(tenancy, confirmed_only=False)
        self._tenancies.append(tenancy)
        self._tenancies.sort(key=lambda t: (t.started_on, t.tenancy_id or 0))
        return tenancy

    def correct(self, corrected: Tenancy) -> Tenancy:
        """Принять исправленный договор на место прежнего.

        Пересечение проверяется только с **подтверждёнными** соседями:
        черновики миграции пересекаются между собой до D3, и требовать от
        владельца распутать их прежде, чем он назовёт одну дату, значило бы
        запереть диалог подтверждения. Подтверждённый договор при этом
        занимает период по-настоящему: вторую дату той же квартиры на те же
        дни подтвердить уже нельзя — это и есть вопрос шага D3.
        """
        self._ensure_free_for(corrected, confirmed_only=True)
        self._tenancies = [corrected if t.tenancy_id == corrected.tenancy_id else t
                           for t in self._tenancies]
        self._tenancies.sort(key=lambda t: (t.started_on, t.tenancy_id or 0))
        return corrected

    def _ensure_free_for(self, tenancy: Tenancy, confirmed_only: bool) -> None:
        others = (t for t in self._tenancies
                  if t.tenancy_id is None or t.tenancy_id != tenancy.tenancy_id)
        if confirmed_only:
            others = (t for t in others if t.start_confirmed)
        clash = next((t for t in others if t.overlaps(tenancy)), None)
        if clash is not None:
            raise PeriodOverlap(
                f"объект #{self.property_id} занят договором #{clash.tenancy_id} "
                f"с {clash.started_on:%d.%m.%Y}")

    def active_on(self, day: date) -> Tenancy | None:
        """Договор, чей период включает день. При пересечении (наследие
        миграции) — самый ранний по дате заселения, затем по номеру."""
        return next((t for t in self._tenancies if t.covers(day)), None)

    def of_record_for(self, period_start: date) -> Tenancy | None:
        """Договор периода — тот, что действовал на дату начала расчётного
        периода ([ADR-0024]). Переезд пятого числа означает, что весь месяц
        будет посчитан на прежнего жильца; пропорциональное деление — P2.

        [ADR-0024]: ../../../docs/architecture/adr/0024-tenancy-of-record-for-period.md
        """
        return self.active_on(period_start)
