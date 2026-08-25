"""Шаг C2b1 плана миграции: у показания появляется ссылка идентификатором.

Первая из трёх фаз стандартной процедуры разрыва cross-module FK (§0 плана):
**FK + ID**. Оба поля живы, читается по-прежнему FK, пишутся оба. Откат
бесплатен: колонку можно удалить, ничего на неё пока не опирается.

То же самое, что миграция `0010` сделала для прибора. Повтор намеренный: две
связи рвутся по отдельности, чтобы каждая имела свою точку отката.
"""

from django.db import migrations, models


def fill_from_the_foreign_key(apps, schema_editor):
    apps.get_model("billing", "MeterReading").objects.update(
        apartment_ref=models.F("apartment_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0011_meter_loses_the_foreign_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="meterreading",
            name="apartment_ref",
            field=models.PositiveIntegerField(
                blank=True, db_index=True, null=True,
                verbose_name="Квартира (идентификатор)"),
        ),
        migrations.RunPython(fill_from_the_foreign_key, migrations.RunPython.noop),
    ]
