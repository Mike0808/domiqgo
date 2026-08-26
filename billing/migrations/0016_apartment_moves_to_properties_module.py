"""Шаг C3b: `billing/` перестаёт владеть объектами недвижимости.

Пара к `properties/0001`. `SeparateDatabaseAndState` без операций над базой:
таблица остаётся, из состояния `billing` модель исчезает.

Два внешних ключа на неё при этом перенацеливаются: `Tenant.apartment` и
`MonthlyStatement.apartment` начинают указывать на `properties.Apartment`.
Констрейнт в базе тот же самый — меняется только то, кому Django считает
принадлежащей целевую модель.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0015_property_is_decommissioned_not_deleted"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="tenant",
                    name="apartment",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tenants", to="properties.apartment"),
                ),
                migrations.AlterField(
                    model_name="monthlystatement",
                    name="apartment",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="statements", to="properties.apartment"),
                ),
                migrations.DeleteModel(name="Apartment"),
            ],
        ),
    ]
