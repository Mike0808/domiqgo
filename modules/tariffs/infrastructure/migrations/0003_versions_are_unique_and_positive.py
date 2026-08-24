"""Инвариант «одна версия на услугу и дату» и «ставка больше нуля» — шаг C1b.

Нарушение №28 гап-анализа. До этой миграции ограничений не было ни в модели,
ни в схеме: две версии одной услуги с одной датой уживались молча, а какая из
них попадёт в счёт, не определялось ничем.

**Миграция намеренно падает на плохих данных.** Выбрать за владельца, какую из
двух версий оставить, нельзя: это разные цены, и разница уедет в счета жильцов.
Поэтому вместо тихой чистки — отказ с перечнем того, что нужно разобрать
руками. Обратная миграция ограничения снимает, так что откатиться и починить
данные можно в любой момент.
"""

from django.db import migrations, models


def refuse_on_data_that_would_violate(apps, schema_editor):
    version = apps.get_model("tariffs", "TariffVersion")

    duplicates = (version.objects
                  .values("utility", "effective_from")
                  .annotate(count=models.Count("id"))
                  .filter(count__gt=1)
                  .order_by("utility", "effective_from"))
    non_positive = (version.objects.filter(rate__lte=0)
                    .order_by("utility", "effective_from"))

    complaints = []
    for row in duplicates:
        rates = ", ".join(
            str(v.rate) for v in version.objects
            .filter(utility=row["utility"], effective_from=row["effective_from"])
            .order_by("id"))
        complaints.append(
            f"  {row['utility']} с {row['effective_from']}: версии со "
            f"ставками {rates}")
    for row in non_positive:
        complaints.append(
            f"  {row.utility} с {row.effective_from}: ставка {row.rate}")

    if complaints:
        raise RuntimeError(
            "Миграция остановлена: в таблице тарифов есть строки, "
            "несовместимые с новыми ограничениями.\n"
            + "\n".join(complaints)
            + "\n\nРазберите их вручную — оставьте по одной версии на услугу "
              "и дату, уберите неположительные ставки — и повторите миграцию. "
              "Выбирать за вас, какую версию оставить, нельзя: это разные "
              "цены, и разница попадёт в счета жильцов."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tariffs", "0002_speak_the_module_language"),
    ]

    operations = [
        migrations.RunPython(refuse_on_data_that_would_violate,
                             migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tariffversion",
            constraint=models.UniqueConstraint(
                fields=("utility", "effective_from"),
                name="tariffs_one_version_per_utility_and_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="tariffversion",
            constraint=models.CheckConstraint(
                condition=models.Q(rate__gt=0),
                name="tariffs_rate_is_positive",
                violation_error_message="Ставка должна быть больше нуля.",
            ),
        ),
    ]
