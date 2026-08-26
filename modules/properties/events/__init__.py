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
from decimal import Decimal


@dataclass(frozen=True)
class PropertyRegistered:
    """Объект заведён в реестре."""

    apartment_id: int
    label: str


@dataclass(frozen=True)
class PropertyServiceCompositionChanged:
    """Состав подведённых услуг или норматив подогрева изменились.

    Подписчика в P1 нет сознательно: изменение состава влияет только на ещё не
    выставленные счета, а уже выставленные защищены неизменяемостью документа
    ([ADR-0005](../../../docs/architecture/adr/0005-retroactive-tariff-correction.md))
    — пересчитывать нечего, и Billing реагировать не должен.

    Прежний состав едет в нагрузке рядом с новым: подписчик должен понять,
    что именно изменилось, не обращаясь обратно в Properties.
    """

    apartment_id: int
    was_cold_water: bool
    was_hot_water: bool
    was_sewage: bool
    now_cold_water: bool
    now_hot_water: bool
    now_sewage: bool
    previous_heat_norm: Decimal
    new_heat_norm: Decimal


@dataclass(frozen=True)
class PropertyDecommissioned:
    """Объект выведен из эксплуатации."""

    apartment_id: int
    decommissioned_on: date


@dataclass(frozen=True)
class PropertyRecommissioned:
    """Объект возвращён в эксплуатацию."""

    apartment_id: int
