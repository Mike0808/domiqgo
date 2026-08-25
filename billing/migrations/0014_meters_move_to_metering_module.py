"""Шаг C2c: `billing/` перестаёт владеть приборами и показаниями.

Пара к `metering/0001`. `SeparateDatabaseAndState` без операций над базой:
таблицы остаются, из состояния `billing` модели исчезают. Порядок задан
`run_before` в парной миграции — принять раньше, чем отдать, нельзя.

Приложение `billing` продолжает читать эти данные, но уже через публичный API
Metering, а не собственные модели.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0013_reading_loses_the_foreign_key"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterUniqueTogether(name="meter", unique_together=set()),
                migrations.AlterUniqueTogether(name="meterreading",
                                               unique_together=set()),
                migrations.DeleteModel(name="Meter"),
                migrations.DeleteModel(name="MeterReading"),
            ],
        ),
    ]
