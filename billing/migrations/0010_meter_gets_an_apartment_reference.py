"""Шаг C2a1 плана миграции: у прибора появляется ссылка идентификатором.

Первая из трёх фаз стандартной процедуры разрыва cross-module FK
(`docs/architecture/04-migration-plan.md`, §0): **FK + ID**. Оба поля живы,
читается по-прежнему FK, пишутся оба. Откат бесплатен: колонку можно удалить,
ничего на неё пока не опирается.

Прибор принадлежит Metering, квартира — Properties. Связь между модулями
выражается идентификатором без констрейнта (правило 1.3): иначе таблицы двух
модулей нельзя разделить, не остановив систему.
"""

from django.db import migrations, models


def fill_from_the_foreign_key(apps, schema_editor):
    apps.get_model("billing", "Meter").objects.update(
        apartment_ref=models.F("apartment_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_tariff_moves_to_tariffs_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="apartment_ref",
            field=models.PositiveIntegerField(
                blank=True, db_index=True, null=True,
                verbose_name="Квартира (идентификатор)"),
        ),
        # Заполнение отдельной операцией, а не `default`: значение у каждой
        # строки своё. Обратной операцией ничего не делаем — колонка уезжает
        # целиком вместе с `AddField`.
        migrations.RunPython(fill_from_the_foreign_key, migrations.RunPython.noop),
    ]
