"""Шаг H2: `billing/` перестаёт владеть платежом.

Пара к `payments/0001`. `SeparateDatabaseAndState` без операций над базой:
таблица остаётся, из состояния `billing` модель исчезает. Порядок задан
`run_before` в парной миграции — принять раньше, чем отдать, нельзя.

Приложение `billing` продолжает показывать платежи в админке и читать их в
статусе счёта, но уже как реэкспортированную модель модуля, а командует ими
только `modules.payments.api`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0026_payment_loses_the_foreign_key"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Payment"),
            ],
        ),
    ]
