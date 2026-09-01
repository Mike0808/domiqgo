"""Шаг D1c: ФИО уходит из профиля жильца.

Пара к `tenancy/0004`, которая перед этим переписывает ФИО в черновики
договоров ещё раз: с D1a до D1c источников было два. Порядок обеспечен
`run_before` в парной миграции: сначала переписать, потом удалять.

Обратная миграция вернёт колонку пустой; ФИО остаётся в договорах.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0018_link_code_moves_to_identity"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="full_name"),
    ]
