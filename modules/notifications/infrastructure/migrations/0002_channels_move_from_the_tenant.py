"""Шаг F1: адреса мессенджера переезжают с жильца на учётную запись.

Канал доставки — не свойство проживания: чат принадлежит человеку, и после
переезда в другую квартиру бот не должен терять его. Переносятся записи, у
которых заполнены обе половины адреса — платформа и чат; половина адреса
адресом не является (принцип C4a).

Один и тот же чат у двух жильцов (старую модель это не смущало) нарушает
инвариант 2 — переносится первый по номеру, остальные перечисляются: этим
людям придётся привязаться заново своим кодом.

Обратная миграция возвращает адреса в профиль жильца, если он ещё есть.
"""

from django.db import migrations


def move_channels_to_the_account(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    channel_model = apps.get_model("notifications", "Channel")

    moved, skipped = 0, []
    seen = set()
    for tenant in (tenant_model.objects.exclude(messenger_platform="")
                   .exclude(messenger_chat_id="").order_by("pk")):
        key = (tenant.messenger_platform, tenant.messenger_chat_id)
        if key in seen or channel_model.objects.filter(
                platform=key[0], address=key[1]).exists():
            skipped.append(tenant.pk)
            continue
        channel_model.objects.create(account_id=tenant.user_id,
                                     platform=key[0], address=key[1])
        seen.add(key)
        moved += 1
    if moved:
        print(f"\n  Каналов доставки перенесено: {moved}.")
    if skipped:
        print(f"  Дубли одного чата у нескольких жильцов: {skipped} — "
              f"перенесён первый, остальным придётся привязаться заново.")


def move_channels_back(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    channel_model = apps.get_model("notifications", "Channel")
    for row in channel_model.objects.all():
        tenant_model.objects.filter(user_id=row.account_id).update(
            messenger_platform=row.platform, messenger_chat_id=row.address)
    channel_model.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_channel_registry"),
        ("billing", "0024_payments_are_voided_not_deleted"),
    ]

    run_before = [
        ("billing", "0025_messenger_moves_to_notifications"),
    ]

    operations = [
        migrations.RunPython(move_channels_to_the_account, move_channels_back),
    ]
