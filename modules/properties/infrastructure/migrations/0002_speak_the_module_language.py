"""Шаг C3b: таблица начинает говорить на языке модуля.

Отдельно от переноса владения (`0001`), чтобы каждая миграция читалась сама по
себе: там сменился владелец, здесь — имя. Правило 5.1 требует префикса по
имени модуля-владельца.

Имя модели остаётся `Apartment`, а не становится `Property`: на P1 объект и
есть квартира, а обобщение отнесено в P3 вместе с домами и коммерческими
помещениями. Подробности — `modules/properties/domain/property.py`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_adopt_billing_apartment"),
        ("billing", "0016_apartment_moves_to_properties_module"),
    ]

    operations = [
        migrations.AlterModelTable(name="apartment",
                                   table="properties_apartment"),
    ]
