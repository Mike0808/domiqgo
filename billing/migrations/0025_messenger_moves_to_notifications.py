"""Шаг F1: адрес мессенджера уходит из профиля жильца.

Пара к `notifications/0002`, которая переносит данные. Порядок обеспечен
`run_before` в парной миграции: сначала переписать, потом удалять.

От `Tenant` остаются только связи — учётная запись и квартира.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0024_payments_are_voided_not_deleted"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="messenger_platform"),
        migrations.RemoveField(model_name="tenant", name="messenger_chat_id"),
    ]
