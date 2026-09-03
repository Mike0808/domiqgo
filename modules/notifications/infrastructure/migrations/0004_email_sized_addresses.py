"""Шаг F4: адреса вмещают почту (254 — предел RFC для адреса).

Ширится и снимок адреса в исходящем сообщении: письмо длиннее номера чата.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_outbox_and_dispatch_journal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channel", name="address",
            field=models.CharField(max_length=254, verbose_name="Адрес"),
        ),
        migrations.AlterField(
            model_name="outgoingmessage", name="address",
            field=models.CharField(max_length=254, verbose_name="Адрес"),
        ),
    ]
