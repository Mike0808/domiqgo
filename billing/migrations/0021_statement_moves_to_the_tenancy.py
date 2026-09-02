"""Шаг E2: счёт переезжает с квартиры на договор (ADR-0024, дефект №6).

**Перед накатом на живой установке обязательна резервная копия** — это
единственный шаг плана, где обратная миграция не восстанавливает исходное
состояние полностью: ключ `(квартира, период)` снимается, и появившиеся после
этого два счёта за один месяц одной квартиры при откате не сожмутся обратно.
На VPS: `deploy/backup-yadisk.sh` до `docker compose up`.

Каждому начислению назначается договор, действовавший на дату начала его
периода, — тем же правилом, каким выбирает договор расчёт (подтверждённый
побеждает черновик, среди черновиков — ранний). Начисления за периоды, когда
договора не было, **остаются без договора**: их нельзя ни отбросить, ни
угадать. Они переносятся с пустым полем, перечисляются в сообщении и видны
владельцу в списке начислений фильтром «без договора» — разбираются вручную.
Миграция на них не падает.
"""

from django.db import migrations, models


def assign_statements_to_their_tenancies(apps, schema_editor):
    statement_model = apps.get_model("billing", "MonthlyStatement")
    tenancy_model = apps.get_model("tenancy", "Tenancy")

    assigned, orphans = 0, []
    for statement in statement_model.objects.all().order_by("pk"):
        covering = [
            t for t in tenancy_model.objects.filter(
                property_id=statement.apartment_id,
                started_on__lte=statement.period)
            if t.ended_on is None or t.ended_on >= statement.period
        ]
        covering.sort(key=lambda t: (not t.start_confirmed, t.started_on, t.pk))
        if covering:
            statement.tenancy_id = covering[0].pk
            statement.save(update_fields=["tenancy_id"])
            assigned += 1
        else:
            orphans.append(f"{statement.apartment_id}/{statement.period:%Y-%m}")

    if assigned:
        print(f"\n  Начислений привязано к договорам: {assigned}.")
    if orphans:
        print(f"  Без договора осталось: {len(orphans)} — {orphans}. Это "
              f"периоды до заведения жильца; видны фильтром «без договора» "
              f"и разбираются вручную.")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0020_payment_gets_an_amount"),
        ("tenancy", "0004_full_names_recopied_before_they_leave"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlystatement", name="tenancy_id",
            field=models.PositiveIntegerField(
                blank=True, db_index=True, null=True, verbose_name="Договор"),
        ),
        migrations.AlterUniqueTogether(name="monthlystatement",
                                       unique_together=set()),
        migrations.AddConstraint(
            model_name="monthlystatement",
            constraint=models.UniqueConstraint(
                condition=models.Q(tenancy_id__isnull=False),
                fields=("tenancy_id", "period"),
                name="one_statement_per_tenancy_period"),
        ),
        migrations.RunPython(assign_statements_to_their_tenancies,
                             migrations.RunPython.noop),
    ]
