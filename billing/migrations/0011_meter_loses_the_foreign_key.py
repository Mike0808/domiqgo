"""Шаг C2a3 плана миграции: внешний ключ на квартиру снят с прибора.

Третья, последняя фаза стандартной процедуры разрыва cross-module FK (§0
плана): **только ID**. Колонка `apartment_ref` становится `apartment_id` и
обязательной, констрейнт исчезает, вместе с ним исчезает и каскад.

Написана руками, а не сгенерирована: `makemigrations` не может знать, что
`apartment_ref` и `apartment_id` — одно и то же поле, и спрашивает об этом
интерактивно. Заодно добавлена проверка данных, которой генератор не делает.

**Что теряется вместе с констрейнтом.** `on_delete=PROTECT` — то, чем закрыт
дефект №9 гап-анализа. Его заменяет явная проверка в `billing/models.py`;
подробности и оговорка к правилу 1.7 — там же, в docstring обработчика.
"""

from django.db import migrations, models


def refuse_on_meters_without_a_reference(apps, schema_editor):
    """Строка без ссылки после этой миграции теряет квартиру безвозвратно.

    Заполнение шло на C2a1 (миграция данных плюс зеркалирование в `save`), но
    строку могли завести в обход — `bulk_create`, `update`, прямой SQL. Пока
    жив внешний ключ, квартиру такой строки ещё можно восстановить; после
    снятия — уже нет. Поэтому отказ, а не догадка.
    """
    orphans = list(apps.get_model("billing", "Meter").objects
                   .filter(apartment_ref__isnull=True)
                   .values_list("id", "kind", "apartment_id"))
    if orphans:
        raise RuntimeError(
            "Миграция остановлена: у части приборов не заполнена ссылка на "
            "квартиру.\n"
            + "\n".join(f"  прибор #{pk} ({kind}) — квартира {apartment}"
                        for pk, kind, apartment in orphans)
            + "\n\nЗаполните `apartment_ref` значением `apartment_id` и "
              "повторите. После снятия внешнего ключа связь этих строк с "
              "квартирой восстановить будет нечем."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_meter_gets_an_apartment_reference"),
    ]

    operations = [
        migrations.RunPython(refuse_on_meters_without_a_reference,
                             migrations.RunPython.noop),
        # Ограничение уникальности снимается первым: оно названо через поле,
        # которое сейчас исчезнет, и переживёт переезд только пересозданным.
        migrations.AlterUniqueTogether(name="meter", unique_together=set()),
        migrations.RemoveField(model_name="meter", name="apartment"),
        migrations.RenameField(model_name="meter", old_name="apartment_ref",
                               new_name="apartment_id"),
        migrations.AlterField(
            model_name="meter",
            name="apartment_id",
            field=models.PositiveIntegerField(db_index=True,
                                              verbose_name="Квартира"),
        ),
        migrations.AlterUniqueTogether(
            name="meter", unique_together={("apartment_id", "kind")}),
    ]
