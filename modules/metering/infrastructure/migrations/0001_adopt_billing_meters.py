"""Шаг C2c: модуль Metering принимает таблицы приборов и показаний.

`SeparateDatabaseAndState` меняет только состояние миграций: Django начинает
считать, что моделями владеет `metering`, а таблицы остаются теми же —
`billing_meter` и `billing_meterreading`. Данные не двигаются, объём их роли
не играет, и откат стоит ровно столько же, сколько накат.

Пара к этой миграции — `billing/0014`, где те же модели удаляются из состояния
`billing`. Порядок обеспечен `run_before`: принять раньше, чем отдать, нельзя —
две модели на одну таблицу Django не допустит.

Модели описаны **такими, какими они были в `billing/`**: поля `kind` и `meter`,
таблицы с прежними именами. Переименование — следующая миграция: перенос
владения и смена языка модуля разведены, чтобы каждая читалась отдельно.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0013_reading_loses_the_foreign_key"),
    ]

    run_before = [
        ("billing", "0014_meters_move_to_metering_module"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Meter",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("apartment_id", models.PositiveIntegerField(
                            db_index=True, verbose_name="Квартира")),
                        ("kind", models.CharField(
                            choices=[("cold_water", "Холодная вода"),
                                     ("hot_water", "Горячая вода"),
                                     ("electricity_single", "Электроэнергия"),
                                     ("electricity_day", "Электроэнергия (день)"),
                                     ("electricity_night", "Электроэнергия (ночь)")],
                            max_length=32, verbose_name="Вид")),
                        ("serial_number", models.CharField(
                            blank=True, max_length=64,
                            verbose_name="Заводской номер")),
                        ("initial_value", models.DecimalField(
                            decimal_places=3, max_digits=12,
                            verbose_name="Начальное показание")),
                        ("initial_date", models.DateField(
                            blank=True,
                            help_text="Дата акта / подписания договора.",
                            null=True, verbose_name="Дата фиксации")),
                    ],
                    options={
                        "verbose_name": "Счётчик",
                        "verbose_name_plural": "Счётчики",
                        "db_table": "billing_meter",
                        "unique_together": {("apartment_id", "kind")},
                    },
                ),
                migrations.CreateModel(
                    name="MeterReading",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("apartment_id", models.PositiveIntegerField(
                            db_index=True, verbose_name="Квартира")),
                        ("period", models.DateField(verbose_name="Период")),
                        ("meter", models.CharField(
                            choices=[("cold_water", "Холодная вода"),
                                     ("hot_water", "Горячая вода"),
                                     ("electricity_single", "Электроэнергия"),
                                     ("electricity_day", "Электроэнергия (день)"),
                                     ("electricity_night", "Электроэнергия (ночь)")],
                            max_length=32, verbose_name="Счётчик")),
                        ("value", models.DecimalField(
                            decimal_places=3, max_digits=12,
                            verbose_name="Показание")),
                        ("entered_by_tenant", models.BooleanField(default=False)),
                    ],
                    options={
                        "verbose_name": "Показание",
                        "verbose_name_plural": "Показания",
                        "db_table": "billing_meterreading",
                        "ordering": ["-period", "meter"],
                        "unique_together": {("apartment_id", "period", "meter")},
                    },
                ),
            ],
        ),
    ]
