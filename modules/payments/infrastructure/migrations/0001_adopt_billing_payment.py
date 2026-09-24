"""Шаг H2: модуль Payments принимает таблицу платежей.

`SeparateDatabaseAndState` меняет только состояние миграций: Django начинает
считать, что моделью владеет `payments`, а таблица остаётся прежней —
`billing_payment`. Данные не двигаются.

Пара к этой миграции — `billing/0027`, где модель удаляется из состояния
`billing`. Порядок обеспечен `run_before`. Ключа на счёт уже нет: его снял
`billing/0026` — принимать cross-module FK модулю запретило бы правило 1.3.

Модель описана такой, какой она стала после `0026`; переименование таблицы —
следующая миграция: перенос владения и смена языка модуля разведены, чтобы
каждая читалась отдельно.
"""

from django.db import migrations, models

from modules.payments.domain import payment as rules
from modules.payments.infrastructure.models import receipt_upload_path


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0026_payment_loses_the_foreign_key"),
    ]

    run_before = [
        ("billing", "0027_payment_moves_to_payments_module"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Payment",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("statement_id", models.PositiveIntegerField(
                            db_index=True, verbose_name="Начисление")),
                        ("file", models.FileField(
                            blank=True, upload_to=receipt_upload_path,
                            verbose_name="Чек")),
                        ("amount", models.DecimalField(
                            blank=True, decimal_places=2, max_digits=12,
                            null=True, verbose_name="Сумма")),
                        ("source", models.CharField(
                            choices=rules.SOURCE_CHOICES, max_length=10,
                            verbose_name="Источник")),
                        ("status", models.CharField(
                            choices=rules.STATUS_CHOICES, default="pending",
                            max_length=10, verbose_name="Статус")),
                        ("note", models.CharField(
                            blank=True, max_length=300,
                            verbose_name="Примечание")),
                        ("submitted_at", models.DateTimeField(
                            auto_now_add=True, verbose_name="Получен")),
                    ],
                    options={
                        "verbose_name": "Платёж",
                        "verbose_name_plural": "Платежи",
                        "db_table": "billing_payment",
                        "ordering": ["-submitted_at"],
                    },
                ),
            ],
        ),
    ]
