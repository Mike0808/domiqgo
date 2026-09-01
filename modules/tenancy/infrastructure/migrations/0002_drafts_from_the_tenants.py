"""Шаг D1a: черновики договоров из записей жильцов.

Из каждой записи `billing.Tenant` создаётся договор: объект и учётная запись
— из связей записи, ФИО — из неё же, условия — с квартиры
(`properties_apartment.rent`, `internet`, `other_fixed`), где они лежали до
сих пор. Это **копия**, а не перенос: до шага D1b условия по-прежнему читаются
с квартиры, и D1b перепишет их в договор ещё раз перед тем, как убрать поля.

**Даты заселения в данных нет, и взять её неоткуда, кроме памяти владельца**
(шаг D2). Миграция ставит дату самого раннего начисления по квартире — она
есть в данных и почти всегда близка к истине, — а если начислений не было,
первое число текущего месяца. В обоих случаях договор помечается
`start_confirmed=False`: черновик, который владелец подтвердит или исправит.
Система при этом работает.

**Квартиры с несколькими жильцами** дают несколько пересекающихся черновиков.
Инвариант непересечения держится на новых договорах, а не на загруженной
истории; развести таких жильцов — шаг D3, и его диалог с владельцем эта
миграция не подменяет. Такие квартиры перечисляются в сообщении.

Признак вывода из эксплуатации переписывается из `decommissioned_on`
квартиры: события, опубликованные до появления подписчика, никто не слышал.

Обратная миграция удаляет черновики и признаки: данные-источники на месте.
"""

from datetime import date

from django.db import migrations


def draft_tenancies_from_the_tenants(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    apartment_model = apps.get_model("properties", "Apartment")
    statement_model = apps.get_model("billing", "MonthlyStatement")
    tenancy_model = apps.get_model("tenancy", "Tenancy")
    out_model = apps.get_model("tenancy", "OutOfService")

    fallback = date.today().replace(day=1)
    drafted, by_apartment, fell_back = 0, {}, []
    for tenant in tenant_model.objects.select_related("apartment").order_by("pk"):
        apartment = tenant.apartment
        first = (statement_model.objects.filter(apartment_id=apartment.pk)
                 .order_by("period").values_list("period", flat=True).first())
        if first is None:
            fell_back.append(tenant.pk)
        tenancy_model.objects.create(
            property_id=apartment.pk, account_id=tenant.user_id,
            full_name=tenant.full_name, started_on=first or fallback,
            start_confirmed=False, rent=apartment.rent,
            internet=apartment.internet, other_fixed=apartment.other_fixed)
        drafted += 1
        by_apartment.setdefault(apartment.pk, []).append(tenant.pk)

    for apartment in apartment_model.objects.exclude(decommissioned_on__isnull=True):
        out_model.objects.get_or_create(property_id=apartment.pk)

    crowded = {a: t for a, t in by_apartment.items() if len(t) > 1}
    if drafted:
        print(f"\n  Черновиков договоров создано: {drafted}. Дата заселения у "
              f"всех не подтверждена — её подтверждает владелец (шаг D2).")
    if fell_back:
        print(f"  У {len(fell_back)} из них начислений не было; поставлено "
              f"{fallback:%d.%m.%Y} — жильцы {fell_back}.")
    if crowded:
        print(f"  Квартир с несколькими жильцами: {len(crowded)} — "
              f"{crowded}. Их черновики пересекаются; развести — шаг D3.")


def drop_the_drafts(apps, schema_editor):
    apps.get_model("tenancy", "Tenancy").objects.all().delete()
    apps.get_model("tenancy", "OutOfService").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_tenancy_register"),
        ("billing", "0018_link_code_moves_to_identity"),
        ("properties", "0004_property_gets_an_address"),
    ]

    operations = [
        migrations.RunPython(draft_tenancies_from_the_tenants, drop_the_drafts),
    ]
