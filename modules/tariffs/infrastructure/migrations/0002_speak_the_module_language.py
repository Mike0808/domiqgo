# Шаг C1: таблица и поле получают имена языка модуля.
#
# Отдельно от переезда намеренно. Предыдущая миграция ничего не делала с базой;
# эта делает — переименовывает колонку и таблицу, — и в диффе видно, что
# именно. Данные не трогаются: переименование не читает и не пишет ни строки.
#
# `utility_type` → `utility`: поле хранит услугу, а не её тип; «Услуга
# (Utility)» — термин из словаря модуля.
# `billing_tariff` → `tariffs_tariff_version`: правило 5.1 требует, чтобы имя
# таблицы начиналось с имени модуля-владельца.
# `ordering` снимается: в as-is порядок был способом выбрать версию, а порядок
# не инвариант. Выбор делает `TariffSchedule.rate_on`.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tariffs", "0001_adopt_billing_tariff"),
        ("billing", "0009_tariff_moves_to_tariffs_module"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tariffversion",
            old_name="utility_type",
            new_name="utility",
        ),
        migrations.AlterModelTable(
            name="tariffversion",
            table="tariffs_tariff_version",
        ),
        migrations.AlterModelOptions(
            name="tariffversion",
            options={"verbose_name": "Версия тарифа", "verbose_name_plural": "Тарифы"},
        ),
        migrations.AlterField(
            model_name="tariffversion",
            name="rate",
            field=models.DecimalField(decimal_places=4, max_digits=10,
                                      verbose_name="Ставка, ₽/ед."),
        ),
    ]
