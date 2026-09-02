"""Договор для тестов, которые выставляют счёт.

С шага D1b счёт без договора периода не выставляется: условия читаются у
договора, а не у квартиры. Тестам, которым нужен счёт, нужен и договор —
заведённый через API Tenancy, как его заведёт владелец.
"""

from datetime import date
from decimal import Decimal

from modules.tenancy import api as tenancy

LONG_AGO = date(2000, 1, 1)


def let_in(apartment, account_id=0, full_name="Жилец", started_on=LONG_AGO,
           rent="0", internet="0", other_fixed="0") -> int:
    """Заселить жильца в квартиру с давнего числа. Возвращает номер договора."""
    return tenancy.start_tenancy(
        apartment.pk, account_id, full_name, started_on,
        tenancy.Terms(rent=Decimal(rent), internet=Decimal(internet),
                      other_fixed=Decimal(other_fixed)))


def draft(apartment, account_id, full_name="Жилец", started_on=LONG_AGO):
    """Черновик договора — строкой таблицы, как его создала миграция D1a.

    В отличие от `let_in`, не проходит доменную проверку непересечения:
    квартира с двумя жильцами после миграции имеет два пересекающихся
    черновика, и оба дают доступ в кабинет — до шага D3.
    """
    from modules.tenancy.infrastructure.models import Tenancy as TenancyRow

    return TenancyRow.objects.create(
        property_id=apartment.pk, account_id=account_id, full_name=full_name,
        started_on=started_on, start_confirmed=False).pk
