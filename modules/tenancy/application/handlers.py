"""Реакция на факты чужих модулей.

Tenancy запоминает вывод объекта из эксплуатации у себя, а не спрашивает
Properties при заключении договора: подписка работает и тогда, когда
Properties недоступен ([ADR-0009]). Действующий договор при выводе не
прекращается — дата выезда должна быть фактом, а не следствием отметки.

[ADR-0009]: ../../../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md
"""

from modules.properties.events import PropertyDecommissioned, PropertyRecommissioned

from .ports import TenancyRepository


def property_decommissioned(repository: TenancyRepository,
                            event: PropertyDecommissioned) -> None:
    repository.mark_out_of_service(event.apartment_id, True)


def property_recommissioned(repository: TenancyRepository,
                            event: PropertyRecommissioned) -> None:
    repository.mark_out_of_service(event.apartment_id, False)
