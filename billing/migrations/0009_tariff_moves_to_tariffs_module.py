# Шаг C1: billing перестаёт владеть тарифами.
#
# Операция только над состоянием: таблица остаётся, её принял модуль Tariffs
# (`tariffs/0001_adopt_billing_tariff`). Первая строка, на которую
# устаревающий слой стал легче — ровно то, что предписывает правило 1.7:
# `billing/` только теряет.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_gvs_heat_norm_help_text"),
        ("tariffs", "0001_adopt_billing_tariff"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Tariff"),
            ],
        ),
    ]
