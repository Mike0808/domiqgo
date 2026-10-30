"""Шаг H3: `billing/` перестаёт владеть счётом, сверкой и политикой.

Пара к `invoicing/0001` (метку «billing» до H4 держит легаси, модуль живёт
под меткой «invoicing»). `SeparateDatabaseAndState` без операций над базой:
таблицы остаются, из состояния `billing` модели исчезают. Порядок задан
`run_before` в парной миграции — принять раньше, чем отдать, нельзя.

У легаси остаются `Tenant` и `Document` — они ждут модуля Documents (P2).
Начисления, сверку и политику приложение продолжает показывать в админке и
читать в кабинете, но уже как реэкспортированные модели модуля, а командует
ими только `modules.billing.api`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0028_statement_loses_the_foreign_key"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="monthlystatement",
                    name="one_statement_per_tenancy_period",
                ),
                migrations.DeleteModel(name="MonthlyStatement"),
                migrations.DeleteModel(name="BillingPolicy"),
                migrations.DeleteModel(name="Settlement"),
            ],
        ),
    ]
