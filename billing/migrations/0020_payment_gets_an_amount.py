"""Шаг E1: у платежа появляется сумма, чек становится необязательным.

Сумма есть только у подтверждённого платежа (инвариант 2 спецификации
Payments) — колонка допускает пустоту. Платежи, подтверждённые до этого
шага, остаются без суммы: их суммы никто не называл, и достроить их неоткуда
— как половину согласия на C4a. Такие платежи перечисляются в сообщении:
сверка этапа E3 попросит владельца указать суммы.

Обратная миграция убирает колонку; суммы при этом теряются — они и
существовали только в ней.
"""

from django.db import migrations, models

import billing.models


def name_confirmed_payments_without_an_amount(apps, schema_editor):
    payment_model = apps.get_model("billing", "Payment")
    nameless = list(payment_model.objects.filter(
        status="confirmed", amount__isnull=True).values_list("pk", flat=True))
    if nameless:
        print(f"\n  Подтверждённых платежей без суммы: {len(nameless)} — "
              f"{nameless}. Их суммы попросит сверка этапа E3.")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0019_full_name_moves_to_tenancy"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment", name="amount",
            field=models.DecimalField(blank=True, decimal_places=2,
                                      max_digits=12, null=True,
                                      verbose_name="Сумма"),
        ),
        migrations.AlterField(
            model_name="payment", name="file",
            field=models.FileField(blank=True,
                                   upload_to=billing.models.receipt_upload_path,
                                   verbose_name="Чек"),
        ),
        migrations.AlterField(
            model_name="payment", name="source",
            field=models.CharField(
                choices=[("telegram", "Telegram"), ("max", "MAX"),
                         ("web", "Веб"), ("manual", "Вручную")],
                max_length=10, verbose_name="Источник"),
        ),
        migrations.RunPython(name_confirmed_payments_without_an_amount,
                             migrations.RunPython.noop),
    ]
