"""Контракты доменных событий модуля: имена и полезная нагрузка.

Импортируются другими модулями наравне с `api/`. Публикуются только из
`application/` (правило 4.4).

Подписчик у обоих событий один и тот же и появится вместе с Tenancy на этапе
**D**: получив `PropertyDecommissioned`, Tenancy запоминает признак и
отказывает в заключении **новых** договоров на этом объекте, не трогая
действующий ([ADR-0009](../../../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md)).
Подписка, а не запрос в момент заключения договора, — чтобы проверка работала
и при недоступности Properties после выделения в сервисы.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PropertyDecommissioned:
    """Объект выведен из эксплуатации."""

    apartment_id: int
    decommissioned_on: date


@dataclass(frozen=True)
class PropertyRecommissioned:
    """Объект возвращён в эксплуатацию."""

    apartment_id: int
