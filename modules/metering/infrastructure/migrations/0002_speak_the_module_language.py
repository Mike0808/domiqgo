"""Шаг C2c: таблицы и поля начинают говорить на языке модуля.

Отдельно от переноса владения (`0001`), чтобы каждая миграция читалась сама
по себе: там сменился владелец, здесь — имена.

`kind` и `meter` становятся `resource`. Второе имя было прямо обманчивым:
поле `MeterReading.meter` хранит не ссылку на прибор, а код того, что прибор
измеряет. Правило 5.1 требует и префикса таблицы по имени модуля-владельца.
"""

from django.db import migrations, models

RESOURCE_CHOICES = [
    ("cold_water", "Холодная вода"),
    ("hot_water", "Горячая вода"),
    ("electricity_single", "Электроэнергия"),
    ("electricity_day", "Электроэнергия (день)"),
    ("electricity_night", "Электроэнергия (ночь)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("metering", "0001_adopt_billing_meters"),
    ]

    operations = [
        # Ограничения сняты первыми: они названы через поля, которые сейчас
        # переименуются, и переживут переезд только пересозданными.
        migrations.AlterUniqueTogether(name="meter", unique_together=set()),
        migrations.AlterUniqueTogether(name="meterreading", unique_together=set()),
        migrations.AlterModelOptions(
            name="meterreading",
            options={"ordering": ["-period", "resource"],
                     "verbose_name": "Показание",
                     "verbose_name_plural": "Показания"},
        ),
        migrations.RenameField(model_name="meter", old_name="kind",
                               new_name="resource"),
        migrations.RenameField(model_name="meterreading", old_name="meter",
                               new_name="resource"),
        migrations.AlterField(
            model_name="meter", name="resource",
            field=models.CharField(choices=RESOURCE_CHOICES, max_length=32,
                                   verbose_name="Вид ресурса"),
        ),
        migrations.AlterField(
            model_name="meterreading", name="resource",
            field=models.CharField(choices=RESOURCE_CHOICES, max_length=32,
                                   verbose_name="Вид ресурса"),
        ),
        migrations.AlterField(
            model_name="meterreading", name="entered_by_tenant",
            field=models.BooleanField(default=False,
                                      verbose_name="Внесено жильцом"),
        ),
        migrations.AlterModelTable(name="meter", table="metering_meter"),
        migrations.AlterModelTable(name="meterreading", table="metering_reading"),
        migrations.AlterUniqueTogether(
            name="meter", unique_together={("apartment_id", "resource")}),
        migrations.AlterUniqueTogether(
            name="meterreading",
            unique_together={("apartment_id", "period", "resource")}),
    ]
