"""Шаг H2: внешний ключ платежа на счёт становится идентификатором.

Тот же трёхтактный приём, что у приборов (`0011`) и показаний (`0013`):
колонка-дубль, перенос значений, снятие ключа, возврат имени. Вместе с ключом
исчезает каскад от удаления счёта — и это соответствует домену: платёж —
свершившийся факт, он не удаляется даже вслед за счётом (инв. 5 Payments).
Осиротеть платёж не может: ключ был NOT NULL, значения переносятся один в
один.

Обратный ход воссоздаёт ключ на пустой колонке и рассчитан на пустую или
свежую таблицу (репетиция отката); на живых данных откат требует обратного
переноса значений руками — как и у предшественников.
"""

from django.db import migrations, models


def copy_references(apps, schema_editor):
    Payment = apps.get_model("billing", "Payment")
    Payment.objects.update(statement_ref=models.F("statement_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0025_messenger_moves_to_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment", name="statement_ref",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(copy_references, migrations.RunPython.noop),
        migrations.RemoveField(model_name="payment", name="statement"),
        migrations.RenameField(model_name="payment", old_name="statement_ref",
                               new_name="statement_id"),
        migrations.AlterField(
            model_name="payment", name="statement_id",
            field=models.PositiveIntegerField(db_index=True,
                                              verbose_name="Начисление"),
        ),
    ]
