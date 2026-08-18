# Журнал опубликованных событий — шаг B2 плана миграции.
#
# Не outbox: поля «доставлено» нет и не будет. Таблица существует ради
# требования ADR-0015 — проекция признанных оплат в Billing обязана быть
# перестраиваемой, а перестраивать её не из чего, если события нигде не
# сохранены.
#
# Откат шага — обратная миграция: на момент её появления таблицу никто не
# читает и записей в ней нет.

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='PublishedEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(db_index=True, max_length=200, verbose_name='Тип события')),
                ('payload', models.JSONField(encoder=django.core.serializers.json.DjangoJSONEncoder, verbose_name='Полезная нагрузка')),
                ('published_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Опубликовано')),
            ],
            options={
                'verbose_name': 'Опубликованное событие',
                'verbose_name_plural': 'Журнал событий',
                'db_table': 'bus_published_event',
                'ordering': ['id'],
            },
        ),
    ]
