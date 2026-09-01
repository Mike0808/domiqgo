"""Шаг D1b: условия переписываются в черновики ещё раз — перед удалением.

С D1a до D1b условия договора существовали в двух местах: на квартире, откуда
их читал Billing, и в черновике договора, куда их скопировала миграция. Правка
карточки квартиры в черновик не попадала. Здесь черновики (и только они —
`start_confirmed=False`: договор, заведённый после D1a через API, свои условия
получил сам) получают условия квартиры заново, и следом `properties/0005`
убирает поля.

Обратная миграция ничего не делает: условия в договорах — уже единственный
источник, и возвращать их на квартиру некуда — `properties/0005` своим
откатом вернёт колонки с нулями.
"""

from django.db import migrations


def recopy_terms_into_the_drafts(apps, schema_editor):
    apartment_model = apps.get_model("properties", "Apartment")
    tenancy_model = apps.get_model("tenancy", "Tenancy")

    updated = 0
    for draft in tenancy_model.objects.filter(start_confirmed=False):
        apartment = apartment_model.objects.filter(pk=draft.property_id).first()
        if apartment is None:
            continue
        draft.rent, draft.internet, draft.other_fixed = (
            apartment.rent, apartment.internet, apartment.other_fixed)
        draft.save(update_fields=["rent", "internet", "other_fixed"])
        updated += 1
    if updated:
        print(f"\n  Условия переписаны в черновики договоров: {updated}.")


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0002_drafts_from_the_tenants"),
        ("properties", "0004_property_gets_an_address"),
    ]

    run_before = [
        ("properties", "0005_terms_leave_for_tenancy"),
    ]

    operations = [
        migrations.RunPython(recopy_terms_into_the_drafts, migrations.RunPython.noop),
    ]
