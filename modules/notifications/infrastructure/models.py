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
    address = models.CharField("Адрес", max_length=254)   # хватает и почте

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


class OutgoingMessage(models.Model):
    """Исходящее сообщение: текст, адресат, судьба доставки.

    Текст и канал зафиксированы при постановке в очередь (инвариант 6) —
    журнал свидетельствует о том, что человек на самом деле получил.
    """

    STATES = [("queued", "В очереди"), ("sent", "Отправлено"),
              ("failed", "Не доставлено"), ("cancelled", "Снято")]

    account_id = models.PositiveIntegerField("Получатель", db_index=True)
    platform = models.CharField("Платформа", max_length=10)
    address = models.CharField("Адрес", max_length=254)   # снимок канала
    text = models.TextField("Текст")
    state = models.CharField("Состояние", max_length=10, choices=STATES,
                             default="queued", db_index=True)
    attempts = models.PositiveSmallIntegerField("Попыток", default=0)
    last_error = models.CharField("Последняя ошибка", max_length=300, blank=True)
    queued_at = models.DateTimeField("Поставлено", auto_now_add=True)

    class Meta:
        db_table = "notifications_message"
        verbose_name = "Исходящее сообщение"
        verbose_name_plural = "Исходящие сообщения"
        ordering = ["queued_at", "id"]

    def __str__(self):
        return f"#{self.account_id} · {self.platform} · {self.get_state_display()}"


class DispatchRun(models.Model):
    """Журнал прогонов отправки — наблюдаемость из плана этапа F.

    Несостоявшийся прогон выглядит не как ошибка, а как тишина; журнал
    делает тишину видимой: последняя строка стареет на глазах у владельца.
    """

    started_at = models.DateTimeField("Начат", auto_now_add=True)
    sent = models.PositiveIntegerField("Доставлено", default=0)
    failed = models.PositiveIntegerField("Не доставлено", default=0)

    class Meta:
        db_table = "notifications_dispatch_run"
        verbose_name = "Прогон отправки"
        verbose_name_plural = "Прогоны отправки"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.started_at:%d.%m %H:%M} — {self.sent} ✓ / {self.failed} ✗"
