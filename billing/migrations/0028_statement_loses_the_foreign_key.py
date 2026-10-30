"""Шаг H3: внешний ключ счёта на квартиру становится идентификатором.

Последний cross-module FK счётного контура, живший с C3b («ключи остаются»,
`properties/0001`). Тот же трёхтактный приём, что у приборов (`0011`),
показаний (`0013`) и платежа (`0026`): колонка-дубль, перенос значений,
снятие ключа, возврат имени. Осиротеть счёт не может: ключ был NOT NULL,
значения переносятся один в один. Вместе с ключом исчезает PROTECT — но
защита и так живёт выше: объект не удаляется, а выводится из эксплуатации
(шаг C3d).

Обратный ход воссоздаёт ключ на пустой колонке и рассчитан на пустую или
свежую таблицу (репетиция отката); на живых данных откат требует обратного
переноса значений руками — как и у предшественников.
"""

from django.db import migrations, models


def copy_references(apps, schema_editor):
    MonthlyStatement = apps.get_model("billing", "MonthlyStatement")
    MonthlyStatement.objects.update(apartment_ref=models.F("apartment_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0027_payment_moves_to_payments_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlystatement", name="apartment_ref",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(copy_references, migrations.RunPython.noop),
        migrations.RemoveField(model_name="monthlystatement",
                               name="apartment"),
        migrations.RenameField(model_name="monthlystatement",
                               old_name="apartment_ref",
                               new_name="apartment_id"),
        migrations.AlterField(
            model_name="monthlystatement", name="apartment_id",
            field=models.PositiveIntegerField(db_index=True,
                                              verbose_name="Квартира"),
        ),
    ]
