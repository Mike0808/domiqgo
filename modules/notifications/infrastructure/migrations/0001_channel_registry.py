"""Шаг F1: реестр каналов доставки.

Оба инварианта канала — ограничениями схемы. Данные переносит следующая
миграция.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Channel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("account_id", models.PositiveIntegerField(
                    db_index=True, verbose_name="Учётная запись")),
                ("platform", models.CharField(max_length=10,
                                              verbose_name="Платформа")),
                ("address", models.CharField(max_length=64,
                                             verbose_name="Адрес")),
            ],
            options={
                "verbose_name": "Канал доставки",
                "verbose_name_plural": "Каналы доставки",
                "db_table": "notifications_channel",
            },
        ),
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(
                fields=("account_id", "platform"),
                name="one_address_per_platform"),
        ),
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(
                fields=("platform", "address"),
                name="one_account_per_address"),
        ),
    ]
