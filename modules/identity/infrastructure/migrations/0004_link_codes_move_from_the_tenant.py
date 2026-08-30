"""Шаг C4c: коды привязки переезжают с жильца на учётную запись.

До этого шага действующий код хранился полем `billing.Tenant.link_code`
(пустая строка — кода нет). Здесь непустые коды переносятся в таблицу
модуля, а следующая миграция `billing/0018` убирает поле у жильца.

**Переносится ровно то, что действует.** Код одноразовый и после погашения
стирался, так что пустое поле — не «нет данных», а «кода нет»; строки для него
не заводится.

Обратная миграция возвращает коды в поле жильца, если оно ещё есть, — порядок
отката обратен накату, `billing/0018` к этому моменту уже вернула колонку.
Код, чья учётная запись не имеет профиля жильца, при откате теряется: у поля
жильца нет места для него, и это называется вслух, а не молча.
"""

from django.db import migrations


def move_link_codes_to_identity(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    link_code_model = apps.get_model("identity", "LinkCode")

    moved = 0
    for tenant in tenant_model.objects.exclude(link_code=""):
        link_code_model.objects.create(account_id=tenant.user_id,
                                       code=tenant.link_code)
        moved += 1
    if moved:
        print(f"\n  Кодов привязки перенесено: {moved}.")


def move_link_codes_back(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    link_code_model = apps.get_model("identity", "LinkCode")

    orphans = []
    for row in link_code_model.objects.all():
        updated = tenant_model.objects.filter(user_id=row.account_id).update(
            link_code=row.code)
        if not updated:
            orphans.append(row.account_id)
    link_code_model.objects.all().delete()
    if orphans:
        print(f"\n  Коды учётных записей без профиля жильца при откате "
              f"потеряны: {orphans}. Их придётся выпустить заново.")


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0003_link_code"),
        ("billing", "0017_consent_moves_to_identity"),
    ]

    run_before = [
        ("billing", "0018_link_code_moves_to_identity"),
    ]

    operations = [
        migrations.RunPython(move_link_codes_to_identity, move_link_codes_back),
    ]
