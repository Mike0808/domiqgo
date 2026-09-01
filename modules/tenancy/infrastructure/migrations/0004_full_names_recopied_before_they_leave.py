"""Шаг D1c: ФИО переписывается в черновики ещё раз — перед удалением.

С D1a до D1c ФИО существовало в двух местах: в профиле жильца, откуда его
читали `Tenant.__str__`, админка и бот, и в черновике договора. Правка
профиля в черновик не попадала. Здесь черновики (и только они —
`start_confirmed=False`) получают ФИО жильца заново, и следом
`billing/0019` убирает поле.

Обратная миграция ничего не делает: ФИО в договорах — уже единственный
источник; `billing/0019` своим откатом вернёт колонку пустой.
"""

from django.db import migrations


def recopy_full_names_into_the_drafts(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    tenancy_model = apps.get_model("tenancy", "Tenancy")

    updated = 0
    for draft in tenancy_model.objects.filter(start_confirmed=False):
        tenant = tenant_model.objects.filter(
            user_id=draft.account_id, apartment_id=draft.property_id).first()
        if tenant is None or tenant.full_name == draft.full_name:
            continue
        draft.full_name = tenant.full_name
        draft.save(update_fields=["full_name"])
        updated += 1
    if updated:
        print(f"\n  ФИО переписаны в черновики договоров: {updated}.")


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0003_terms_recopied_before_they_leave"),
        ("billing", "0018_link_code_moves_to_identity"),
    ]

    run_before = [
        ("billing", "0019_full_name_moves_to_tenancy"),
    ]

    operations = [
        migrations.RunPython(recopy_full_names_into_the_drafts,
                             migrations.RunPython.noop),
    ]
