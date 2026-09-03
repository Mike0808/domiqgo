"""Хранение каналов доставки. Единственное место модуля, знающее о базе.

Ссылка на учётную запись — идентификатором без констрейнта (правило 1.3).
"""

from django.db import models


class Channel(models.Model):
    """Привязка учётной записи к адресу в платформе.

    Оба инварианта канала — ограничениями схемы: не более одного адреса на
    платформу у записи (инв. 1) и один адрес — одной записи (инв. 2).
    """

    account_id = models.PositiveIntegerField("Учётная запись", db_index=True)
    platform = models.CharField("Платформа", max_length=10)
    address = models.CharField("Адрес", max_length=64)

    class Meta:
        db_table = "notifications_channel"
        verbose_name = "Канал доставки"
        verbose_name_plural = "Каналы доставки"
        constraints = [
            models.UniqueConstraint(fields=("account_id", "platform"),
                                    name="one_address_per_platform"),
            models.UniqueConstraint(fields=("platform", "address"),
                                    name="one_account_per_address"),
        ]

    def __str__(self):
        return f"#{self.account_id}: {self.platform}:{self.address}"
