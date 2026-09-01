"""Шаг C4e: реестр учётных записей с типом — владелец или жилец.

До этого шага «кто передо мной» решал флаг `is_staff` Django в двух
представлениях. Здесь заводится реестр, и все существующие записи
классифицируются один раз по тому же правилу: персонал — владелец, остальные
— жильцы. Поведение не меняется; меняется, кто отвечает на вопрос.

Записи, которых реестр не знает (заведённые после миграции стандартной
админкой), получают тип тем же мостом при чтении — см.
`domain.type_from_staff_flag`.

Обратная миграция удаляет реестр; флаг `is_staff` никуда не девался, и
представления прежних версий вернутся к нему сами.
"""

from django.db import migrations, models


def classify_existing_accounts(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    account_model = apps.get_model("identity", "Account")

    owners = tenants = 0
    for user in user_model.objects.all().only("pk", "is_staff"):
        account_model.objects.create(
            account_id=user.pk, type="owner" if user.is_staff else "tenant")
        if user.is_staff:
            owners += 1
        else:
            tenants += 1
    if owners or tenants:
        print(f"\n  Учётных записей зарегистрировано: владельцев {owners}, "
              f"жильцов {tenants}.")


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0004_link_codes_move_from_the_tenant"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("account_id", models.PositiveIntegerField(
                    unique=True, verbose_name="Учётная запись")),
                ("type", models.CharField(
                    choices=[("owner", "Владелец"), ("tenant", "Жилец")],
                    max_length=10, verbose_name="Тип")),
            ],
            options={
                "verbose_name": "Учётная запись",
                "verbose_name_plural": "Учётные записи",
                "db_table": "identity_account",
            },
        ),
        migrations.RunPython(classify_existing_accounts,
                             migrations.RunPython.noop),
    ]
