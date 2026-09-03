from decimal import Decimal

from django.conf import settings
from django.db import models

# Объект недвижимости принадлежит Properties (шаг C3b). Здесь он нужен только
# как цель двух оставшихся внешних ключей; читать его поля следует через
# `modules.properties.api`.
from modules.properties.infrastructure.models import Apartment

# `Apartment` уехал в `modules/properties/` шагом C3b: домен, публичный API,
# события. Таблица переименована в `properties_apartment`. Читать объект
# отсюда следует через `modules.properties.api`; два внешних ключа на него
# пока остаются — `Tenant.apartment` ждёт Tenancy (этап D),
# `MonthlyStatement.apartment` — шага E2, где ключом счёта станет договор.

class Tenant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="tenant")
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="tenants")
    # ФИО уехало в договор (D1c, ADR-0010), согласие и код привязки — в
    # Identity (C4a, C4c), адрес мессенджера — в Notifications (F1): канал
    # доставки принадлежит учётной записи, а не проживанию. От профиля
    # остались связи; их разберёт расформирование `billing/`.

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    @property
    def display_name(self) -> str:
        """ФИО из действующего договора учётной записи, иначе имя входа.

        Спрашивается у Tenancy на сегодняшний день: «сегодня» — понятие
        интерфейса, и модуль его не читает сам.
        """
        from django.utils import timezone
        from modules.tenancy import api as tenancy

        contract = tenancy.active_tenancy_for_account(self.user_id, timezone.localdate())
        if contract is not None and contract.full_name:
            return contract.full_name
        return self.user.get_username()

    def __str__(self):
        return self.display_name

# `Tariff` уехал в modules/tariffs/ шагом C1: у него не было ни одного FK и на
# него не ссылалась ни одна модель, поэтому лист графа отделился без разрыва
# связей. Ставки читаются через `modules.tariffs.api.get_rates_on`.

# `METER_KIND_CHOICES`, `Meter` и `MeterReading` уехали в
# `modules/metering/` шагом C2c плана миграции. Таблицы переименованы в
# `metering_meter` и `metering_reading`; словарь стал каталогом видов ресурса
# `modules/metering/domain/catalogue.py`. Читать их отсюда следует только
# через `modules.metering.api`.

class MonthlyStatement(models.Model):
    #: Статус — не поле, а результат сверки (шаг E3, ADR-0015, дефект №15):
    #: признанные суммы сравниваются с итогом. Константы остались — ими
    #: говорят шаблоны, портал и тесты.
    UNPAID = "unpaid"; PENDING = "pending"; PAID = "paid"
    STATUS_LABELS = {UNPAID: "Не оплачено", PENDING: "На проверке",
                     PAID: "Оплачено"}

    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="statements")
    #: Договор, которому выставлен счёт (шаг E2, ADR-0024) — идентификатором,
    #: без FK. Пусто у начислений за периоды до заведения жильца: такие
    #: разбираются владельцем вручную (фильтр «без договора» в админке).
    tenancy_id = models.PositiveIntegerField("Договор", null=True, blank=True,
                                             db_index=True)
    period = models.DateField("Период")
    lines = models.JSONField("Строки начисления", default=list)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2, default=Decimal("0"))
    #: Момент предъявления (шаг E4, дефект №35). Пусто — черновик: он
    #: пересчитывается сколько угодно, его никто не предъявлял. Выставленный
    #: счёт неизменяем (инв. 2 Billing).
    issued_at = models.DateTimeField("Выставлен", null=True, blank=True)
    #: Срок оплаты фиксируется в счёте значением в момент выставления
    #: (ADR-0013): смена политики не делает старые счета просроченными.
    due_date = models.DateField("Оплатить до", null=True, blank=True)

    class Meta:
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
        """Погашен, если признано не меньше итога; «на проверке», пока есть
        заявленный платёж. Частичная оплата счёт не закрывает — в этом смысл
        сверки (Q3 карты: «хватило ли»)."""
        settled = self.settled_total
        if settled > 0 and settled >= self.total:
            return self.PAID
        if self.payments.filter(status=Payment.PENDING).exists():
            return self.PENDING
        return self.UNPAID

    def get_status_display(self) -> str:
        """Имя как у поля с choices — шаблоны не заметили исчезновения
        колонки."""
        return self.STATUS_LABELS[self.status]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} — {self.total} ₽"


class BillingPolicy(models.Model):
    """Политика срока оплаты — единая для всех счетов установки (ADR-0013).

    Число дней от выставления; на P2, когда договоры станут разными, срок
    переедет в Tenancy — ожидаемое развитие, а не исправление ошибки.
    """

    due_days = models.PositiveSmallIntegerField("Дней на оплату", default=10)

    class Meta:
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
        verbose_name = "Сверка оплат"
        verbose_name_plural = "Сверка оплат"

    def __str__(self):
        return f"Счёт #{self.statement_id}: признано {self.confirmed_total} ₽"

def document_upload_path(instance, filename):
    return f"documents/tenant_{instance.tenant_id}/{filename}"

class Document(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("Файл", upload_to=document_upload_path)
    title = models.CharField("Название", max_length=200, default="Договор аренды")
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def __str__(self):
        return self.title

def receipt_upload_path(instance, filename):
    return f"receipts/statement_{instance.statement_id}/{filename}"

class Payment(models.Model):
    TELEGRAM = "telegram"; MAX = "max"; WEB = "web"; MANUAL = "manual"
    SOURCE_CHOICES = [(TELEGRAM, "Telegram"), (MAX, "MAX"), (WEB, "Веб"),
                      (MANUAL, "Вручную")]
    PENDING = "pending"; CONFIRMED = "confirmed"; REJECTED = "rejected"
    VOIDED = "voided"
    #: «Отменён» — не то же, что «отклонён»: отклоняют незнакомца, чья сумма
    #: в сверке не участвовала; отменяют признанный платёж, и его сумма
    #: изымается из сверки (шаг E5, дефект №16).
    STATUS_CHOICES = [
        (PENDING, "На проверке"), (CONFIRMED, "Подтверждён"),
        (REJECTED, "Отклонён"), (VOIDED, "Отменён"),
    ]

    statement = models.ForeignKey(MonthlyStatement, on_delete=models.CASCADE,
                                  related_name="payments")
    #: Чек необязателен (шаг E1): владелец отмечает наличную оплату вручную,
    #: не прося фотографию ради формальности.
    file = models.FileField("Чек", upload_to=receipt_upload_path, blank=True)
    #: Подтверждённая сумма. Есть только у подтверждённого платежа (инв. 2
    #: спецификации Payments); у заявленного чека суммы ещё нет. Пусто у
    #: платежей, подтверждённых до шага E1, — их суммы никто не называл, и
    #: выдумать их нельзя; сверка этапа E3 попросит владельца их указать.
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2,
                                 null=True, blank=True)
    source = models.CharField("Источник", max_length=10, choices=SOURCE_CHOICES)
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=PENDING)
    note = models.CharField("Примечание", max_length=300, blank=True)
    submitted_at = models.DateTimeField("Получен", auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Платёж {self.statement} ({self.get_status_display()})"
