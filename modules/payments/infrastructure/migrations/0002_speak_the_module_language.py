"""Шаг H2: таблица платежей начинает говорить на языке модуля.

Отдельно от переноса владения (`0001`), чтобы каждая миграция читалась сама
по себе: там сменился владелец, здесь — имя. Правило 5.1 требует префикса
таблицы по имени модуля-владельца.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_adopt_billing_payment"),
    ]

    operations = [
        migrations.AlterModelTable(name="payment", table="payments_payment"),
    ]
