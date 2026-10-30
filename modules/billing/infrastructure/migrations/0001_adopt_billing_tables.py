"""Шаг H3: модуль Billing принимает таблицы счёта, сверки и политики.

`SeparateDatabaseAndState` меняет только состояние миграций: Django начинает
считать, что моделями владеет `invoicing` (метка модуля Billing; метку
«billing» до H4 держит легаси), а таблицы остаются прежними. Данные не
двигаются.

Пара к этой миграции — `billing/0029`, где те же модели удаляются из
состояния `billing`. Порядок обеспечен `run_before`. Ключа на квартиру уже
нет: его снял `billing/0028` — принимать cross-module FK модулю запретило бы
правило 1.3.

Переименования таблиц не будет: `billing_*` уже носит префикс владельца
(правило 5.1 — префикс по имени каталога `modules/billing`).
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0028_statement_loses_the_foreign_key"),
    ]

    run_before = [
        ("billing", "0029_billing_moves_to_its_module"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="MonthlyStatement",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("apartment_id", models.PositiveIntegerField(
                            db_index=True, verbose_name="Квартира")),
                        ("tenancy_id", models.PositiveIntegerField(
                            blank=True, db_index=True, null=True,
                            verbose_name="Договор")),
                        ("period", models.DateField(verbose_name="Период")),
                        ("lines", models.JSONField(
                            default=list, verbose_name="Строки начисления")),
                        ("total", models.DecimalField(
                            decimal_places=2, default=Decimal("0"),
                            max_digits=12, verbose_name="Итого")),
                        ("issued_at", models.DateTimeField(
                            blank=True, null=True, verbose_name="Выставлен")),
                        ("due_date", models.DateField(
                            blank=True, null=True,
                            verbose_name="Оплатить до")),
                    ],
                    options={
                        "verbose_name": "Начисление",
                        "verbose_name_plural": "Начисления",
                        "db_table": "billing_monthlystatement",
                        "ordering": ["-period"],
                    },
                ),
                migrations.AddConstraint(
                    model_name="monthlystatement",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(tenancy_id__isnull=False),
                        fields=("tenancy_id", "period"),
                        name="one_statement_per_tenancy_period"),
                ),
                migrations.CreateModel(
                    name="BillingPolicy",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("due_days", models.PositiveSmallIntegerField(
                            default=10, verbose_name="Дней на оплату")),
                    ],
                    options={
                        "verbose_name": "Политика счетов",
                        "verbose_name_plural": "Политика счетов",
                        "db_table": "billing_billingpolicy",
                    },
                ),
                migrations.CreateModel(
                    name="Settlement",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True,
                                                   primary_key=True,
                                                   serialize=False,
                                                   verbose_name="ID")),
                        ("statement_id", models.PositiveIntegerField(
                            unique=True, verbose_name="Начисление")),
                        ("confirmed_total", models.DecimalField(
                            decimal_places=2, default=Decimal("0"),
                            max_digits=12, verbose_name="Признано")),
                    ],
                    options={
                        "verbose_name": "Сверка оплат",
                        "verbose_name_plural": "Сверка оплат",
                        "db_table": "billing_settlement",
                    },
                ),
            ],
        ),
    ]
