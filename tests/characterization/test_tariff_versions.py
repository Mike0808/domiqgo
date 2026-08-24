"""Тарифная линия: пункт №28 гап-анализа.

| Пункт | Что зафиксировано                                         | Кто переписал |
|-------|-----------------------------------------------------------|---------------|
| №28   | ~~две версии на одну услугу и дату уживаются молча~~ → вторая отклоняется | **C1b** |
| №28   | ~~ставка может быть нулевой и отрицательной~~ → только больше нуля        | **C1b** |

Пункт не помечен ⚠ и в каталог шага A3 не попал: он классифицирован как
**БД** — «требует изменения схемы», а критерием отбора было «меняется
поведение». Отбор оказался узок, и тест был заведён отдельным коммитом перед
самим шагом, чтобы правка была видна в диффе.

**Что стало.** Инвариант живёт в `TariffSchedule` и проверяется без базы;
ограничения `tariffs_one_version_per_utility_and_date` и
`tariffs_rate_is_positive` подпирают его в схеме на случай записи мимо модуля.
Данные, несовместимые с ограничениями, миграция `0003` не чистит, а
отказывается применяться: выбрать за владельца, какую из двух версий
оставить, нельзя — это разные цены, и разница уедет в счета жильцов.

**Чего этот тест больше не утверждает.** Прежняя редакция фиксировала, что
выбор одной из двух версий не определён ничем, и намеренно не проверяла,
какая выиграет. Утверждение исчезло вместе с самой возможностью: двух версий
на одну дату теперь не бывает.
"""

from datetime import date
from decimal import Decimal

import pytest

from modules.tariffs import api
from modules.tariffs.infrastructure.models import TariffVersion

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]

JULY = date(2026, 7, 1)


def test_second_version_on_the_same_date_is_refused():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(api.DuplicateVersion):
        api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)


def test_the_refusal_says_what_to_do_instead():
    """Отказ обязан объяснять выбор: исправить существующую версию или
    завести новую с другой датой. Это два разных события реального мира, и
    владелец должен понять, какое из них у него."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(api.DuplicateVersion) as refusal:
        api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)

    assert "исправьте существующую версию" in str(refusal.value).lower()
    assert "другую дату" in str(refusal.value)


def test_the_refused_version_leaves_no_trace():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(api.DuplicateVersion):
        api.publish_tariff_version("cold_water", Decimal("55.00"), JULY)

    assert TariffVersion.objects.filter(utility="cold_water").count() == 1
    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")


def test_correcting_a_date_onto_an_occupied_one_is_refused():
    """Второй способ получить дубликат — переехать датой на занятую."""
    api.publish_tariff_version("cold_water", Decimal("40.00"), date(2026, 1, 1))
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(api.DuplicateVersion):
        api.correct_tariff_version("cold_water", JULY,
                                   effective_from=date(2026, 1, 1))

    assert [v.effective_from for v in api.list_versions("cold_water")] == [
        date(2026, 1, 1), JULY]


def test_zero_rate_is_refused():
    with pytest.raises(api.InvalidRate):
        api.publish_tariff_version("cold_water", Decimal("0"), JULY)


def test_negative_rate_is_refused():
    with pytest.raises(api.InvalidRate):
        api.publish_tariff_version("cold_water", Decimal("-10.00"), JULY)


def test_correcting_a_rate_down_to_zero_is_refused():
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(api.InvalidRate):
        api.correct_tariff_version("cold_water", JULY, rate=Decimal("0"))

    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")


def test_the_database_refuses_a_duplicate_too():
    """Ограничение в схеме — не украшение: запись мимо модуля тоже
    отклоняется. Это последняя черта на случай миграции данных или правки
    руками, а правило по-прежнему живёт в домене."""
    from django.db import IntegrityError

    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)

    with pytest.raises(IntegrityError):
        TariffVersion.objects.create(
            utility="cold_water", rate=Decimal("55.00"), effective_from=JULY)


@pytest.mark.parametrize("rate", ["0", "-10.00"])
def test_the_database_refuses_a_bad_rate_too(rate):
    """Вторая черта, отдельная от первой: `objects.create` не зовёт ни домен,
    ни `full_clean`, и без ограничения в схеме нулевая ставка легла бы
    молча."""
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        TariffVersion.objects.create(
            utility="cold_water", rate=Decimal(rate), effective_from=JULY)
