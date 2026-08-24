"""Сборка тарифной линии из строк и обратно.

Репозиторий — единственный переводчик между агрегатом и таблицей. Слой
`application/` работает с линией и не знает, что она где-то лежит; слой
`domain/` не знает и того, что есть репозиторий.
"""

from datetime import date

from django.db import transaction

from ..domain.catalogue import UTILITIES
from ..domain.schedule import TariffSchedule, TariffVersion
from . import models


def load(utility: str) -> TariffSchedule:
    """Линия целиком: инвариант «одна версия на дату» многоверсионный, и
    проверить его на куске невозможно."""
    rows = models.TariffVersion.objects.filter(utility=utility)
    return TariffSchedule(utility, [_to_domain(row) for row in rows])


@transaction.atomic
def save(schedule: TariffSchedule) -> None:
    """Записать линию: удалить прежние строки услуги и вставить нынешние.

    Грубо, но честно, и оставлено сознательно. Сопоставить версию со строкой
    можно было бы по дате начала действия: после шага C1b она уникальна, и
    прежнее возражение — «сопоставление молча потеряет дубликат» — отпало.
    Переход всё же не сделан, и по двум причинам. Первая: это правка
    без изменения поведения, а C1b поведение меняет, и складывать их в один
    шаг — то самое, что запрещает правило 7.4. Вторая: выигрыш меньше, чем
    кажется. Устойчивыми стали бы ключи нетронутых строк, но у только что
    заведённой версии ключа всё равно нет — объект формы его не знает, — так
    что перечитывание строки в админке никуда не девается.

    Цена — первичные ключи строк меняются при каждой записи. Ни одна модель на
    тариф не ссылается (в этом и была причина начать выделение с Tariffs), а
    счёт хранит применённую ставку значением, поэтому платить нечем. Всё под
    `atomic`: между удалением и вставкой линии не существует.

    Линия целиком помещается в память: версий у услуги единицы, регулятор
    меняет цену дважды в год.
    """
    models.TariffVersion.objects.filter(utility=schedule.utility).delete()
    models.TariffVersion.objects.bulk_create(
        models.TariffVersion(
            utility=version.utility, rate=version.rate,
            effective_from=version.effective_from,
            source_name=version.source_name, source_url=version.source_url,
        )
        for version in schedule.versions
    )


def rates_on(on_date: date) -> dict[str, TariffVersion]:
    """Действующие на дату версии по всем услугам каталога — один запрос
    вместо N. Услуги без ставки в ответе отсутствуют."""
    rows = (models.TariffVersion.objects
            .filter(effective_from__lte=on_date)
            .order_by("utility", "effective_from"))
    # Позже по дате — позже в выборке, поэтому последняя запись услуги и есть
    # действующая. Правило то же, что в `TariffSchedule.rate_on`, но применить
    # там его нельзя: линий здесь семь, а грузить их целиком ради одной даты
    # значит вычитать всю историю цен на каждый счёт.
    latest: dict[str, TariffVersion] = {}
    for row in rows:
        if row.utility in UTILITIES:
            latest[row.utility] = _to_domain(row)
    return latest


def _to_domain(row) -> TariffVersion:
    return TariffVersion(
        utility=row.utility, rate=row.rate, effective_from=row.effective_from,
        source_name=row.source_name, source_url=row.source_url)
