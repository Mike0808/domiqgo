"""Шаг D1a: реестр договоров и признак вывода объекта из эксплуатации.

Данные переносит следующая миграция.
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenancy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("property_id", models.PositiveIntegerField(
                    db_index=True, verbose_name="Объект")),
                ("account_id", models.PositiveIntegerField(
                    db_index=True, verbose_name="Учётная запись")),
                ("full_name", models.CharField(
                    blank=True, max_length=200, verbose_name="ФИО")),
                ("started_on", models.DateField(verbose_name="Заселение")),
                ("ended_on", models.DateField(
                    blank=True, null=True, verbose_name="Выезд")),
                ("start_confirmed", models.BooleanField(
                    default=True, verbose_name="Дата заселения подтверждена")),
                ("rent", models.DecimalField(
                    decimal_places=2, default=Decimal("0"), max_digits=10,
                    verbose_name="Аренда")),
                ("internet", models.DecimalField(
                    decimal_places=2, default=Decimal("0"), max_digits=10,
                    verbose_name="Интернет")),
                ("other_fixed", models.DecimalField(
                    decimal_places=2, default=Decimal("0"), max_digits=10,
                    verbose_name="Прочее")),
            ],
            options={
                "verbose_name": "Договор",
                "verbose_name_plural": "Договоры",
                "db_table": "tenancy_tenancy",
                "ordering": ["property_id", "started_on", "id"],
            },
        ),
        migrations.CreateModel(
            name="OutOfService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("property_id", models.PositiveIntegerField(
                    unique=True, verbose_name="Объект")),
            ],
            options={
                "verbose_name": "Объект вне эксплуатации",
                "verbose_name_plural": "Объекты вне эксплуатации",
                "db_table": "tenancy_out_of_service",
            },
        ),
    ]
