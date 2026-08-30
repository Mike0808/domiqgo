"""Шаг C4c: код привязки уходит из профиля жильца.

Пара к `identity/0004`, которая переносит данные. Порядок обеспечен `run_before`
в парной миграции: сначала переписать, потом удалять.

Обратная миграция вернёт колонку пустой; коды в неё возвращает откат
`identity/0004`, который Django выполнит следом.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0017_consent_moves_to_identity"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="link_code"),
    ]
