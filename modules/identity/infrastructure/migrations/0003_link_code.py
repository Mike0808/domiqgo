"""Шаг C4c: таблица кодов привязки.

Одна строка на учётную запись, пока код действует; погашение — удаление
строки. Данные переносит следующая миграция.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0002_consents_move_from_the_tenant"),
    ]

    operations = [
        migrations.CreateModel(
            name="LinkCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("account_id", models.PositiveIntegerField(
                    unique=True, verbose_name="Учётная запись")),
                ("code", models.CharField(max_length=32, unique=True,
                                          verbose_name="Код")),
            ],
            options={
                "verbose_name": "Код привязки",
                "verbose_name_plural": "Коды привязки",
                "db_table": "identity_link_code",
            },
        ),
    ]
