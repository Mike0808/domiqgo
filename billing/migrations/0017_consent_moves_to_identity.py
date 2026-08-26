"""Шаг C4a: согласие уходит из профиля жильца.

Пара к `identity/0002`, которая переносит данные. Порядок обеспечен `run_before`
в парной миграции: сначала переписать, потом удалять.

Обратная миграция вернёт колонки пустыми. Восстановить в них согласия она не
пытается: журнал допускает несколько записей на учётную запись, а пара полей —
одну, и выбирать за оператора, какое согласие считать единственным, нельзя.
Данные при этом не теряются — они остаются в журнале, пока не откатят и
`identity/0002`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0016_apartment_moves_to_properties_module"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="privacy_consent_at"),
        migrations.RemoveField(model_name="tenant",
                               name="privacy_consent_version"),
    ]
