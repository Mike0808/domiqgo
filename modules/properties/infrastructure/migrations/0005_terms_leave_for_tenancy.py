"""Шаг D1b: условия договора уходят с квартиры.

Пара к `tenancy/0003`, которая перед этим переписывает условия в черновики
договоров ещё раз: с D1a до D1b источников было два, и правка карточки
квартиры в черновик не попадала. Порядок обеспечен `run_before` в парной
миграции: сначала переписать, потом удалять.

Обратная миграция вернёт колонки с нулями; условия при этом остаются в
договорах, пока не откатят и `tenancy/0003`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0004_property_gets_an_address"),
    ]

    operations = [
        migrations.RemoveField(model_name="apartment", name="rent"),
        migrations.RemoveField(model_name="apartment", name="internet"),
        migrations.RemoveField(model_name="apartment", name="other_fixed"),
    ]
