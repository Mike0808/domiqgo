"""Тарифная линия — корень агрегата Tariffs.

Корень — **линия**, а не отдельная версия: инвариант «не две версии на одну
дату» охватывает несколько версий сразу, и держать его может только объект,
который видит их все. Отвергнут вариант «версия как самостоятельный корень с
уникальным индексом в БД»: тогда правило живёт в схеме, а не в домене, и
`domain/`, которому запрещено знать про ORM, не может его ни проверить, ни
протестировать (спецификация модуля, «Владение данными»).

Здесь только stdlib. Ни Django, ни базы: линию можно собрать из списка версий
и спросить у неё ставку на дату, не поднимая ничего.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from .catalogue import ensure_known


@dataclass(frozen=True)
class TariffVersion:
    """Ставка с датой начала действия. Конца действия нет — версию закрывает
    следующая, поэтому «до какого числа» вычисляет линия, а не версия."""

    utility: str
    rate: Decimal
    effective_from: date
    source_name: str = ""
    source_url: str = ""


class VersionNotFound(LookupError):
    """В линии нет версии, начинающейся с этой даты."""


class TariffSchedule:
    """Вся история цен на одну услугу."""

    def __init__(self, utility: str, versions=()):
        self.utility = ensure_known(utility)
        # Порядок держит линия, а не хранилище: `Meta.ordering` как способ
        # выбора версии из as-is убран сознательно — порядок не инвариант,
        # инвариант — «действующая на дату».
        self._versions: list[TariffVersion] = sorted(
            versions, key=lambda v: v.effective_from)

    @property
    def versions(self) -> list[TariffVersion]:
        """Все версии по возрастанию даты начала действия."""
        return list(self._versions)

    def rate_on(self, on_date: date) -> TariffVersion | None:
        """Версия с наибольшим «действует с», не превышающим дату.

        `None` — нормальный результат, а не ошибка: ставки на эту дату просто
        нет. Как это трактовать, решает Billing (сейчас превращает в
        `MissingTariffError` и показывает жильцу «Тариф не настроен»).
        """
        applicable = [v for v in self._versions if v.effective_from <= on_date]
        return applicable[-1] if applicable else None

    def effective_range(self, effective_from: date) -> tuple[date, date | None]:
        """Отрезок действия версии: с её даты до даты следующей, не включая.

        Нужен `TariffVersionCorrected`: по [ADR-0005](../../../docs/architecture/adr/0005-retroactive-tariff-correction.md)
        Billing помечает затронутые счета сам, и найти их он должен, **не
        обращаясь обратно в Tariffs**. Значит отрезок обязан приехать в
        payload события — и вычислить его может только линия.
        """
        version = self._require(effective_from)
        index = self._versions.index(version)
        following = self._versions[index + 1:]
        return version.effective_from, following[0].effective_from if following else None

    # ---------------------------------------------------------------- команды

    def publish(self, rate: Decimal, effective_from: date,
                source_name: str = "", source_url: str = "") -> TariffVersion:
        """Ввести новую ставку. Дата может быть в будущем — ставку с 1 июля
        владелец заводит в июне."""
        version = TariffVersion(
            utility=self.utility, rate=rate, effective_from=effective_from,
            source_name=source_name, source_url=source_url)
        self._insert(version)
        return version

    def correct(self, was_effective_from: date, *,
                rate: Decimal | None = None,
                effective_from: date | None = None,
                source_name: str | None = None,
                source_url: str | None = None) -> tuple[TariffVersion, TariffVersion]:
        """Исправить опечатку в уже введённой версии.

        Смысл — «этой версии не должно было быть такой», а не «цена
        изменилась». Различение принципиально: первое признаёт ошибку
        оператора, второе фиксирует исторический факт, и на уже выставленные
        счета они влияют по-разному. Отсюда две команды и два события.

        Версию опознаёт `was_effective_from` — дата, с которой она действует
        **сейчас**; `effective_from` среди изменений означает новую дату.
        Разные имена именно поэтому: править дату по самой дате иначе не
        выразить. `None` значит «не менять», а не «очистить».

        Возвращает пару «было, стало»: событию нужна прежняя ставка.
        """
        previous = self._require(was_effective_from)
        changes = {name: value for name, value in (
            ("rate", rate), ("effective_from", effective_from),
            ("source_name", source_name), ("source_url", source_url),
        ) if value is not None}
        corrected = replace(previous, **changes)
        self._versions.remove(previous)
        try:
            self._insert(corrected)
        except Exception:
            self._insert(previous)   # линия не должна остаться без версии
            raise
        return previous, corrected

    def withdraw(self, effective_from: date) -> TariffVersion:
        """Убрать версию, введённую по ошибке.

        В линии допустимо не остаться ни одной версии: услуга без ставки —
        законное состояние, `rate_on` вернёт `None`.
        """
        version = self._require(effective_from)
        self._versions.remove(version)
        return version

    # ------------------------------------------------------------ внутреннее

    def _insert(self, version: TariffVersion) -> None:
        self._versions.append(version)
        self._versions.sort(key=lambda v: v.effective_from)

    def _require(self, effective_from: date) -> TariffVersion:
        for version in self._versions:
            if version.effective_from == effective_from:
                return version
        raise VersionNotFound(
            f"У услуги «{self.utility}» нет версии, действующей с "
            f"{effective_from:%d.%m.%Y}")
