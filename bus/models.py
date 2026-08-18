"""Журнал опубликованных событий — шаг B2 плана миграции.

**Это не transactional outbox.** Outbox отнесён к P2 и решает другую задачу —
гарантию доставки: отдельный процесс читает необработанные записи и досылает
их. Здесь записей никто не вычитывает, поля «доставлено» нет и не будет.

Журнал существует ради одного требования:
[ADR-0015](../docs/architecture/adr/0015-settlement-projection-in-billing.md)
разрешает Billing держать проекцию признанных оплат — вторую копию величины,
которой владеет Payments, — **при условии, что проекция перестраиваема**.
Перестраивать её не из чего, если события нигде не сохранены.
"""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class PublishedEvent(models.Model):
    """Факт публикации: что, с какой нагрузкой и когда.

    Записывается **в той же транзакции**, что и само изменение: откат уносит
    журнальную запись вместе с фактом, которого не было. Этим журнал и
    отличается от outbox, который обязан пережить откат доставки, но не откат
    транзакции.
    """

    #: Полное имя класса события — `modules.billing.events.InvoiceIssued`.
    #: Строка, а не импорт: шина по-прежнему не знает ни одного события
    #: (контракт `bus-knows-no-domain`).
    event_type = models.CharField("Тип события", max_length=200, db_index=True)

    #: `DjangoJSONEncoder` укладывает `Decimal` и `date` в строки — при
    #: пересборке их придётся разобрать обратно. Потери точности нет: и
    #: «1234.56», и «2026-07-01» разбираются однозначно.
    payload = models.JSONField("Полезная нагрузка", encoder=DjangoJSONEncoder)

    published_at = models.DateTimeField("Опубликовано", auto_now_add=True,
                                        db_index=True)

    class Meta:
        db_table = "bus_published_event"
        # Порядок пересборки — порядок вставки. По времени сортировать нельзя:
        # два события одной транзакции получают неразличимую метку.
        ordering = ["id"]
        verbose_name = "Опубликованное событие"
        verbose_name_plural = "Журнал событий"

    def __str__(self):
        return f"{self.event_type} #{self.pk}"
