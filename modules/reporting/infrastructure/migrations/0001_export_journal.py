"""Шаг G1: журнал выгрузок — кто и когда выгружал персональные данные."""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ExportRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("report_code", models.CharField(max_length=20,
                                                 verbose_name="Отчёт")),
                ("initiated_by", models.PositiveIntegerField(
                    verbose_name="Инициатор")),
                ("scope", models.CharField(max_length=200,
                                           verbose_name="Область")),
                ("state", models.CharField(
                    choices=[("started", "Начата"), ("succeeded", "Выполнена"),
                             ("failed", "Не удалась")],
                    default="started", max_length=10, verbose_name="Исход")),
                ("error", models.CharField(blank=True, max_length=300,
                                           verbose_name="Ошибка")),
                ("started_at", models.DateTimeField(auto_now_add=True,
                                                    verbose_name="Начата")),
            ],
            options={"verbose_name": "Выгрузка",
                     "verbose_name_plural": "Журнал выгрузок",
                     "db_table": "reporting_export_run",
                     "ordering": ["-started_at"]},
        ),
    ]
