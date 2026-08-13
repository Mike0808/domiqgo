# Дефект №29: подсказка к полю теперь говорит, что норматив обязателен.
#
# `default=Decimal("0")` сознательно оставлен: убрать его — значит потребовать
# значение от уже заведённых квартир, а взять его негде (величина подомовая,
# из квитанции УК). Обязательность выражена проверкой `Apartment.clean`, а не
# схемой. Ничего, кроме текста подсказки, эта миграция не меняет.

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_apartment_deletion_is_protected'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apartment',
            name='gvs_heat_norm',
            field=models.DecimalField(decimal_places=5, default=Decimal('0'), help_text='Тепло на подогрев 1 м³ горячей воды — см. квитанцию УК (обычно 0,05–0,065 Гкал/м³). Обязателен, если подведена горячая вода: без него подогрев не начислится.', max_digits=7, verbose_name='Норматив подогрева ГВС, Гкал/м³'),
        ),
    ]
