"""Шаг F2: очередь исходящих и журнал прогонов отправки."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_channels_move_from_the_tenant"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutgoingMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("account_id", models.PositiveIntegerField(
                    db_index=True, verbose_name="Получатель")),
                ("platform", models.CharField(max_length=10, verbose_name="Платформа")),
                ("address", models.CharField(max_length=64, verbose_name="Адрес")),
                ("text", models.TextField(verbose_name="Текст")),
                ("state", models.CharField(
                    choices=[("queued", "В очереди"), ("sent", "Отправлено"),
                             ("failed", "Не доставлено"), ("cancelled", "Снято")],
                    db_index=True, default="queued", max_length=10,
                    verbose_name="Состояние")),
                ("attempts", models.PositiveSmallIntegerField(
                    default=0, verbose_name="Попыток")),
                ("last_error", models.CharField(
                    blank=True, max_length=300, verbose_name="Последняя ошибка")),
                ("queued_at", models.DateTimeField(
                    auto_now_add=True, verbose_name="Поставлено")),
            ],
            options={"verbose_name": "Исходящее сообщение",
                     "verbose_name_plural": "Исходящие сообщения",
                     "db_table": "notifications_message",
                     "ordering": ["queued_at", "id"]},
        ),
        migrations.CreateModel(
            name="DispatchRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True,
                                                    verbose_name="Начат")),
                ("sent", models.PositiveIntegerField(default=0,
                                                     verbose_name="Доставлено")),
                ("failed", models.PositiveIntegerField(default=0,
                                                       verbose_name="Не доставлено")),
            ],
            options={"verbose_name": "Прогон отправки",
                     "verbose_name_plural": "Прогоны отправки",
                     "db_table": "notifications_dispatch_run",
                     "ordering": ["-started_at"]},
        ),
    ]
