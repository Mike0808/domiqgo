"""Шаг E3: статус счёта исчезает как поле — погашение выводит сверка.

Дефект №15 (ADR-0015): платёжный поток буквально проставлял
`MonthlyStatement.status`, и счёт можно было объявить оплаченным, не имея ни
одного платежа. Теперь погашение — сравнение признанных сумм с итогом.

Три перевода существующих фактов, с их датами — как согласия на C4a:

1. Подтверждённый платёж без суммы на счёте со статусом «оплачено» получает
   сумму, равную итогу счёта: старое поле утверждало ровно «оплачен
   полностью», и перевод этого утверждения в сумму — не выдумка, а смена
   формы. Второй и последующие безсуммовые платежи одного счёта остаются
   без суммы и перечисляются: их доли неизвестны.
2. Каждое подтверждение с суммой записывается в журнал шины событием
   `PaymentConfirmed` со своей датой (`submitted_at`): проекция обязана быть
   перестраиваемой из журнала, а событий старше шага E3 в нём нет.
3. Проекция `billing_settlement` заполняется суммами подтверждённого.

Счёт, чьё поле говорило «оплачено», а платежей с суммами не нашлось вовсе,
перечисляется отдельно: после наката он честно показывается неоплаченным,
и владелец отмечает оплату вручную (`RecordPayment`) — выдумывать платёж,
которого нет в фактах, миграция не вправе.

Обратная миграция возвращает колонку и выводит её значение из проекции.
"""

from django.db import migrations, models


def translate_the_stored_statuses(apps, schema_editor):
    statement_model = apps.get_model("billing", "MonthlyStatement")
    payment_model = apps.get_model("billing", "Payment")
    settlement_model = apps.get_model("billing", "Settlement")
    journal_model = apps.get_model("bus", "PublishedEvent")

    amounts_translated, nameless, unpaid_now = 0, [], []
    for statement in statement_model.objects.all().order_by("pk"):
        confirmed = list(statement.payments.filter(status="confirmed")
                         .order_by("pk"))
        if statement.status == "paid":
            sumless = [p for p in confirmed if p.amount is None]
            if sumless and all(p.amount is None for p in confirmed):
                sumless[0].amount = statement.total
                sumless[0].save(update_fields=["amount"])
                amounts_translated += 1
                nameless.extend(p.pk for p in sumless[1:])
            elif not confirmed:
                unpaid_now.append(f"{statement.apartment_id}/{statement.period:%Y-%m}")

        total = sum((p.amount for p in confirmed if p.amount is not None),
                    start=0)
        for payment in confirmed:
            if payment.amount is None:
                continue
            journal_model.objects.create(
                event_type="modules.payments.events.PaymentConfirmed",
                payload={"payment_id": payment.pk, "statement_id": statement.pk,
                         "amount": str(payment.amount),
                         "at": payment.submitted_at.isoformat()})
        if total:
            settlement_model.objects.create(statement_id=statement.pk,
                                            confirmed_total=total)

    if amounts_translated:
        print(f"\n  Платежей получили сумму из старого «оплачено»: "
              f"{amounts_translated}.")
    if nameless:
        print(f"  Остались без суммы (доли неизвестны): платежи {nameless}.")
    if unpaid_now:
        print(f"  Счета со старым «оплачено» без единого платежа: {unpaid_now} "
              f"— теперь показываются неоплаченными; отметьте оплату вручную.")


def restore_the_column_from_the_projection(apps, schema_editor):
    statement_model = apps.get_model("billing", "MonthlyStatement")
    settlement_model = apps.get_model("billing", "Settlement")
    settled = {row.statement_id: row.confirmed_total
               for row in settlement_model.objects.all()}
    for statement in statement_model.objects.all():
        amount = settled.get(statement.pk, 0)
        if amount and amount >= statement.total:
            statement.status = "paid"
        elif statement.payments.filter(status="pending").exists():
            statement.status = "pending"
        else:
            statement.status = "unpaid"
        statement.save(update_fields=["status"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0021_statement_moves_to_the_tenancy"),
        ("bus", "0001_published_event_journal"),
    ]

    operations = [
        migrations.CreateModel(
            name="Settlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("statement_id", models.PositiveIntegerField(
                    unique=True, verbose_name="Начисление")),
                ("confirmed_total", models.DecimalField(
                    decimal_places=2, default=0, max_digits=12,
                    verbose_name="Признано")),
            ],
            options={"verbose_name": "Сверка оплат",
                     "verbose_name_plural": "Сверка оплат"},
        ),
        migrations.RunPython(translate_the_stored_statuses,
                             restore_the_column_from_the_projection),
        migrations.RemoveField(model_name="monthlystatement", name="status"),
    ]
