"""Шаг C2b3 плана миграции: внешний ключ на квартиру снят с показания.

Третья, последняя фаза разрыва второй связи. Колонка `apartment_ref`
становится `apartment_id` и обязательной, констрейнт исчезает, вместе с ним
исчезает и каскад. Приборы прошли этот путь миграцией `0011`.

**Страж здесь строже по смыслу, хотя код тот же.** Прибор без ссылки после
разрыва просто теряется, и расчёт останавливается: без прибора нет базы
отсчёта (`MissingBaselineError`). Показание без ссылки не останавливает
ничего — база отсчёта откатывается к начальному значению прибора, расход
выходит больше настоящего, и счёт жильцу растёт молча. Догадка здесь
недопустима вдвойне.
"""

from django.db import migrations, models


def refuse_on_readings_without_a_reference(apps, schema_editor):
    orphans = list(apps.get_model("billing", "MeterReading").objects
                   .filter(apartment_ref__isnull=True)
                   .values_list("id", "period", "meter", "apartment_id"))
    if orphans:
        raise RuntimeError(
            "Миграция остановлена: у части показаний не заполнена ссылка на "
            "квартиру.\n"
            + "\n".join(
                f"  показание #{pk} ({meter} за {period}) — квартира {apartment}"
                for pk, period, meter, apartment in orphans)
            + "\n\nЗаполните `apartment_ref` значением `apartment_id` и "
              "повторите. Показание, потерявшее квартиру, не обнаружит себя "
              "ошибкой: база отсчёта молча откатится к начальному значению "
              "прибора, и счёт жильцу вырастет."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0012_reading_gets_an_apartment_reference"),
    ]

    operations = [
        migrations.RunPython(refuse_on_readings_without_a_reference,
                             migrations.RunPython.noop),
        migrations.AlterUniqueTogether(name="meterreading", unique_together=set()),
        migrations.RemoveField(model_name="meterreading", name="apartment"),
        migrations.RenameField(model_name="meterreading",
                               old_name="apartment_ref", new_name="apartment_id"),
        migrations.AlterField(
            model_name="meterreading",
            name="apartment_id",
            field=models.PositiveIntegerField(db_index=True,
                                              verbose_name="Квартира"),
        ),
        migrations.AlterUniqueTogether(
            name="meterreading",
            unique_together={("apartment_id", "period", "meter")}),
    ]
