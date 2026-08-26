"""Шаг C4a: согласия переезжают с жильца на учётную запись.

До этого шага согласие хранилось двумя полями `billing.Tenant` —
`privacy_consent_at` и `privacy_consent_version`. Здесь они переносятся в
журнал, а следующая миграция `billing/0017` убирает их из жильца.

**Даты сохраняются, а не проставляются заново.** Согласие — факт во времени, и
подменить его момент датой переезда значило бы подделать то самое
доказательство, ради которого оно хранится.

**Переносится ровно то, что было.** Жилец, у которого стояла дата, но не
стояла редакция (или наоборот), в журнал не попадает: половина факта фактом не
является, а достроить недостающую половину неоткуда. Такие строки
пересчитываются в отдельном сообщении — их владелец увидит при накате.

Обратная миграция не восстанавливает поля жильца: она удаляет журнал, а поля
возвращает `billing/0017` своим откатом. Порядок отката обратен накату, и
Django выстроит его сам.
"""

from django.db import migrations


def move_consents_to_the_journal(apps, schema_editor):
    tenant_model = apps.get_model("billing", "Tenant")
    consent_model = apps.get_model("identity", "Consent")

    moved, incomplete = 0, []
    rows = tenant_model.objects.exclude(
        privacy_consent_at__isnull=True, privacy_consent_version="")
    for tenant in rows:
        if tenant.privacy_consent_at is None or not tenant.privacy_consent_version:
            incomplete.append(tenant.pk)
            continue
        consent_model.objects.create(
            account_id=tenant.user_id,
            policy_version=tenant.privacy_consent_version,
            given_at=tenant.privacy_consent_at)
        moved += 1

    if incomplete:
        print(f"\n  Согласий перенесено: {moved}. Пропущено записей с "
              f"половиной факта (есть дата без редакции или наоборот): "
              f"{len(incomplete)} — жильцы {incomplete}. Такое согласие "
              f"доказательством не является; этих людей придётся спросить "
              f"заново.")


def empty_the_journal(apps, schema_editor):
    apps.get_model("identity", "Consent").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0001_consent_journal"),
        ("billing", "0016_apartment_moves_to_properties_module"),
    ]

    run_before = [
        ("billing", "0017_consent_moves_to_identity"),
    ]

    operations = [
        migrations.RunPython(move_consents_to_the_journal, empty_the_journal),
    ]
