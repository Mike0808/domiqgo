# Шаг C1: модель переезжает из billing/ в modules/tariffs/, база не трогается.
#
# `SeparateDatabaseAndState` без единой операции над базой: таблица
# `billing_tariff` остаётся ровно там же и такой же, меняется только то, какое
# приложение считает её своей. Модель здесь описана **как она есть сегодня** —
# с полем `utility_type` и прежней таблицей; приведение к языку модуля идёт
# следующей миграцией, отдельной, чтобы переезд и переименование не смешались
# в одном диффе.
#
# Порядок: сначала эта миграция объявляет модель в tariffs, затем billing/0009
# убирает её у себя. Между ними состояние знает о двух моделях на одной
# таблице — это допустимо, потому что ни одна из миграций базы не касается.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0008_gvs_heat_norm_help_text"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="TariffVersion",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                                   serialize=False, verbose_name="ID")),
                        ("utility_type", models.CharField(
                            choices=[
                                ("cold_water", "Холодная вода"),
                                ("hot_water_cold_component", "ГВС — компонент на холодную воду"),
                                ("hot_water_heat_component", "ГВС — компонент на тепловую энергию"),
                                ("sewage", "Водоотведение"),
                                ("electricity_single", "Электроэнергия"),
                                ("electricity_day", "Электроэнергия (день)"),
                                ("electricity_night", "Электроэнергия (ночь)"),
                            ],
                            max_length=32, verbose_name="Услуга")),
                        ("rate", models.DecimalField(decimal_places=4, max_digits=10,
                                                     verbose_name="Тариф, ₽/ед.")),
                        ("effective_from", models.DateField(verbose_name="Действует с")),
                        ("source_name", models.CharField(blank=True, max_length=200,
                                                         verbose_name="Источник")),
                        ("source_url", models.URLField(blank=True,
                                                       verbose_name="Ссылка на источник")),
                    ],
                    options={
                        "db_table": "billing_tariff",
                        "verbose_name": "Тариф",
                        "verbose_name_plural": "Тарифы",
                        "ordering": ["utility_type", "-effective_from"],
                    },
                ),
            ],
        ),
    ]
