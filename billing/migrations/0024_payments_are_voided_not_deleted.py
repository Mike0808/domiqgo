"""Шаг E5: у платежа появляется состояние «отменён».

Дефект №16: удаление платежа стирало и запись, и файл — разбирательство
«а я платил» становилось нечем подкрепить. Отмена сохраняет обоих и
фиксирует причину; сумма изымается из сверки событием `PaymentVoided`.
Данных миграция не трогает — меняется только словарь состояний.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0023_invoices_are_issued_not_implied"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment", name="status",
            field=models.CharField(
                choices=[("pending", "На проверке"), ("confirmed", "Подтверждён"),
                         ("rejected", "Отклонён"), ("voided", "Отменён")],
                default="pending", max_length=10, verbose_name="Статус"),
        ),
    ]
