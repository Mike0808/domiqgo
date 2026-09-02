"""Шаг E4: у счёта появляется момент предъявления и срок оплаты.

Дефект №35: счёт возникал сам и предъявленным считался по умолчанию — момента
не существовало. Существующие счета помечаются выставленными моментом наката:
жильцы их видели и по ним платили, факт предъявления был, а его момента никто
не записывал — записать «сейчас» честнее, чем оставить прежние счета
черновиками и молча закрыть жильцам оплату. Срок оплаты у них остаётся
пустым: политика в момент их настоящего предъявления неизвестна, и просрочка
по ним не вычисляется никогда (ADR-0013: срок фиксируется значением в момент
выставления).

Замки периодов не трогаются: закрытие периода — часть нового предъявления, а
не переписывание старых месяцев.

Обратная миграция убирает колонки; черновики при этом перестают отличаться
от выставленных — как и было до шага.
"""

from django.db import migrations, models
from django.utils import timezone


def mark_existing_invoices_as_issued(apps, schema_editor):
    statement_model = apps.get_model("billing", "MonthlyStatement")
    now = timezone.now()
    marked = statement_model.objects.filter(issued_at=None).update(issued_at=now)
    if marked:
        print(f"\n  Существующих счетов помечено выставленными: {marked} "
              f"(моментом наката; срок оплаты пуст — просрочка по ним не "
              f"вычисляется).")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0022_status_becomes_a_reconciliation"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlystatement", name="issued_at",
            field=models.DateTimeField(blank=True, null=True,
                                       verbose_name="Выставлен"),
        ),
        migrations.AddField(
            model_name="monthlystatement", name="due_date",
            field=models.DateField(blank=True, null=True,
                                   verbose_name="Оплатить до"),
        ),
        migrations.CreateModel(
            name="BillingPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("due_days", models.PositiveSmallIntegerField(
                    default=10, verbose_name="Дней на оплату")),
            ],
            options={"verbose_name": "Политика счетов",
                     "verbose_name_plural": "Политика счетов"},
        ),
        migrations.RunPython(mark_existing_invoices_as_issued,
                             migrations.RunPython.noop),
    ]
