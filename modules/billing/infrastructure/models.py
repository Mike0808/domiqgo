"""Модели счётного контура — деталь хранения модуля Billing (шаг H3).

Таблицы приняты из легаси парой миграций по образцу Metering/Properties/
Payments; имена не менялись — `billing_*` и так носит префикс владельца
(правило 5.1: префикс — имя каталога модуля, а не метка приложения). Ссылки
на объект и договор — идентификаторы без констрейнтов (правило 1.3): ключ
на квартиру снял `billing/0028`.

Имена классов тоже остались легасийными: язык модуля живёт на границе —
`api/` и `events/` говорят «invoice», — а переименование класса стоило бы
правок ContentType, прав и журнала админки ради косметики.
"""

from decimal import Decimal

from django.db import models

from ..domain import invoice as rules
from . import claims


class MonthlyStatement(models.Model):
    #: Статус — не поле, а результат сверки (шаг E3, ADR-0015, дефект №15):
    #: признанные суммы сравниваются с итогом. Константы остались — ими
    #: говорят шаблоны, портал и тесты.
    UNPAID = rules.UNPAID; PENDING = rules.PENDING; PAID = rules.PAID
    STATUS_LABELS = rules.STATUS_LABELS

    #: Объект — идентификатором (правило 1.3): объектом владеет Properties.
    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    #: Договор, которому выставлен счёт (шаг E2, ADR-0024) — идентификатором,
    #: без FK. Пусто у начислений за периоды до заведения жильца: такие
    #: разбираются владельцем вручную (фильтр «без договора» в админке).
    tenancy_id = models.PositiveIntegerField("Договор", null=True, blank=True,
                                             db_index=True)
    period = models.DateField("Период")
    lines = models.JSONField("Строки начисления", default=list)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2,
                                default=Decimal("0"))
    #: Момент предъявления (шаг E4, дефект №35). Пусто — черновик: он
    #: пересчитывается сколько угодно, его никто не предъявлял. Выставленный
    #: счёт неизменяем (инв. 2 Billing).
    issued_at = models.DateTimeField("Выставлен", null=True, blank=True)
    #: Срок оплаты фиксируется в счёте значением в момент выставления
    #: (ADR-0013): смена политики не делает старые счета просроченными.
    due_date = models.DateField("Оплатить до", null=True, blank=True)

    class Meta:
        db_table = "billing_monthlystatement"
        verbose_name = "Начисление"
        verbose_name_plural = "Начисления"
        # Ключ счёта — (договор, период), а не (квартира, период): смена
        # жильца в середине месяца даёт два счёта рядом (шаг E2, дефект №6).
        constraints = [models.UniqueConstraint(
            condition=models.Q(tenancy_id__isnull=False),
            fields=("tenancy_id", "period"),
            name="one_statement_per_tenancy_period")]
        ordering = ["-period"]

    @property
    def is_issued(self) -> bool:
        return self.issued_at is not None

    @property
    def settled_total(self) -> Decimal:
        """Признанная оплата — из проекции, которую ведёт сверка (E3)."""
        row = Settlement.objects.filter(statement_id=self.pk).first()
        return row.confirmed_total if row is not None else Decimal("0")

    @property
    def status(self) -> str:
        """Погашен, если признано не меньше итога (правило — в домене).
        «На проверке» — знание Payments; его провайдер внедрён интерфейсом
        (`infrastructure/claims.py`)."""
        return rules.settled_status(self.settled_total, self.total,
                                    claims.has_pending_claim(self.pk))

    def get_status_display(self) -> str:
        """Имя как у поля с choices — шаблоны не заметили исчезновения
        колонки."""
        return self.STATUS_LABELS[self.status]

    def __str__(self):
        from modules.properties import api as properties

        obj = properties.get_property(self.apartment_id)
        label = obj.label if obj is not None else f"объект #{self.apartment_id}"
        return f"{label} {self.period:%Y-%m} — {self.total} ₽"


class BillingPolicy(models.Model):
    """Политика срока оплаты — единая для всех счетов установки (ADR-0013).

    Число дней от выставления; на P2, когда договоры станут разными, срок
    переедет в Tenancy — ожидаемое развитие, а не исправление ошибки.
    """

    due_days = models.PositiveSmallIntegerField("Дней на оплату", default=10)

    class Meta:
        db_table = "billing_billingpolicy"
        verbose_name = "Политика счетов"
        verbose_name_plural = "Политика счетов"

    @classmethod
    def get(cls) -> "BillingPolicy":
        row = cls.objects.first()
        return row if row is not None else cls.objects.create()

    def __str__(self):
        return f"Срок оплаты: {self.due_days} дн. от выставления"


class Settlement(models.Model):
    """Проекция признанных оплат по счёту (ADR-0015).

    Строится исключительно из событий PaymentConfirmed и PaymentVoided и
    обязана быть перестраиваемой из журнала шины — `RebuildSettlement`.
    Осознанное дублирование: источник истины по платежам — платёжный контур,
    но спрашивать его Billing не может, не замкнув цикл (ADR-0014).
    """

    statement_id = models.PositiveIntegerField("Начисление", unique=True)
    confirmed_total = models.DecimalField(
        "Признано", max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        db_table = "billing_settlement"
        verbose_name = "Сверка оплат"
        verbose_name_plural = "Сверка оплат"

    def __str__(self):
        return f"Счёт #{self.statement_id}: признано {self.confirmed_total} ₽"
