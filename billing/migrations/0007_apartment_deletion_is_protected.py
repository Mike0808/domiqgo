# Дефект №9 гап-анализа: квартира без жильца удалялась бесшумно, унося
# приборы, показания и все выставленные счета. `PROTECT` стоял только на
# жильце, а жильца удалить можно — то есть защиты не было вообще.
#
# Схему это не меняет: on_delete живёт в Python, ни один констрейнт БД не
# переписывается. Миграция нужна только чтобы состояние совпало с моделями.
#
# Полный запрет удаления объекта и «вывод из эксплуатации» вместо него —
# шаг C3 плана миграции; здесь закрыта только потеря данных.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_tenant_privacy_consent_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='meter',
            name='apartment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='meters', to='billing.apartment'),
        ),
        migrations.AlterField(
            model_name='meterreading',
            name='apartment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='readings', to='billing.apartment'),
        ),
        migrations.AlterField(
            model_name='monthlystatement',
            name='apartment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='statements', to='billing.apartment'),
        ),
    ]
