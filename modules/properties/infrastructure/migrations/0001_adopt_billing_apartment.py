"""Шаг C3b: модуль Properties принимает таблицу объектов недвижимости.

`SeparateDatabaseAndState` меняет только состояние миграций: Django начинает
считать, что моделью владеет `properties`, а таблица остаётся прежней —
`billing_apartment`. Данные не двигаются.

Пара к этой миграции — `billing/0016`, где модель удаляется из состояния
`billing`, а два внешних ключа на неё — `Tenant.apartment` и
`MonthlyStatement.apartment` — перенацеливаются на новое место. Порядок
обеспечен `run_before`.

**Ключи остаются.** Разорвать их здесь нельзя: первый ждёт Tenancy (этап D),
второй — шага E2, где ключом счёта становится договор. До тех пор в схеме живёт
cross-module FK; правило 1.3 запрещает такие ключи в новом коде, а
существующие велит рвать шагами плана, что и происходит.
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0015_property_is_decommissioned_not_deleted"),
    ]

    run_before = [
        ("billing", "0016_apartment_moves_to_properties_module"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Apartment",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("label", models.CharField(max_length=200,
                                                   verbose_name="Квартира")),
                        ("decommissioned_on", models.DateField(
                            blank=True,
                            help_text="Пусто — объект в эксплуатации.",
                            null=True,
                            verbose_name="Выведен из эксплуатации")),
                        ("electricity_meter_type", models.CharField(
                            choices=[("single", "Однотарифный"),
                                     ("dual", "День/Ночь")],
                            default="single", max_length=10,
                            verbose_name="Тип счётчика электроэнергии")),
                        ("has_cold_water", models.BooleanField(
                            default=True, verbose_name="Холодная вода")),
                        ("has_hot_water", models.BooleanField(
                            default=True, verbose_name="Горячая вода")),
                        ("has_sewage", models.BooleanField(
                            default=True, verbose_name="Водоотведение")),
                        ("gvs_heat_norm", models.DecimalField(
                            decimal_places=5, default=Decimal("0"),
                            help_text="Тепло на подогрев 1 м³ горячей воды — "
                                      "см. квитанцию УК (обычно 0,05–0,065 "
                                      "Гкал/м³). Обязателен, если подведена "
                                      "горячая вода: без него подогрев не "
                                      "начислится.",
                            max_digits=7,
                            verbose_name="Норматив подогрева ГВС, Гкал/м³")),
                        ("round_total", models.BooleanField(
                            default=True,
                            help_text="Итог свыше 10 000 ₽ округляется вниз до "
                                      "кратного 50 ₽ (строка «Округление» в "
                                      "квитанции).",
                            verbose_name="Округлять итог")),
                        ("rent", models.DecimalField(
                            decimal_places=2, default=Decimal("0"),
                            max_digits=10, verbose_name="Аренда")),
                        ("internet", models.DecimalField(
                            decimal_places=2, default=Decimal("0"),
                            max_digits=10, verbose_name="Интернет")),
                        ("other_fixed", models.DecimalField(
                            decimal_places=2, default=Decimal("0"),
                            max_digits=10, verbose_name="Прочее")),
                    ],
                    options={
                        "verbose_name": "Квартира",
                        "verbose_name_plural": "Квартиры",
                        "db_table": "billing_apartment",
                    },
                ),
            ],
        ),
    ]
