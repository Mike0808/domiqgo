from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError

def _refuse_if_history_remains(apartment_ids):
    """Временная замена `on_delete=PROTECT`, снятого вместе с внешним ключом.

    Защита квартиры от удаления вместе со всей историей — это [дефект
    №9](../docs/architecture/03-gap-analysis.md), закрытый миграцией `0007`.
    Держался он на `on_delete`, то есть на том самом констрейнте, который
    шаг C2a3 убирает. Вернуть его запросом из Properties нельзя: Properties —
    лист графа зависимостей и обращаться к Metering не вправе. В целевой
    модели вопрос снимается на **C3**, где удаление квартиры заменяется
    выводом из эксплуатации; до тех пор правило держит эта проверка.

    Правило 1.7 запрещает `billing/` получать новые правила. Здесь правило не
    новое: то же самое, выраженное иначе, потому что прежнее выражение
    исчезло вместе с констрейнтом. Альтернатива — вернуть уже закрытый дефект
    с потерей данных на несколько шагов плана.

    **Проверка стоит до удаления, а не в `pre_delete`.** Сигнал срабатывает
    внутри транзакции удаления, и отказ из него оставляет её непригодной:
    следующий же запрос падает с `TransactionManagementError`. Настоящий
    `PROTECT` проверяет раньше, на сборе связанных объектов, — и вызывающий
    после отказа продолжает работать. Отличие вскрылось тестом; повторять
    поведение надо целиком, иначе «то же правило, выраженное иначе»
    превращается в другое правило.
    """
    ids = list(apartment_ids)
    meters = Meter.objects.filter(apartment_id__in=ids)
    if meters.exists():
        raise ProtectedError(
            "Нельзя удалить квартиру, за которой числятся приборы учёта.",
            set(meters))
    readings = MeterReading.objects.filter(apartment_id__in=ids)
    if readings.exists():
        raise ProtectedError(
            "Нельзя удалить квартиру, за которой числятся показания счётчиков.",
            set(readings))


class ApartmentQuerySet(models.QuerySet):
    """Удаление списком — тот путь, которым удаляет админка, выделив квартиры
    галочками. Переопределения `Model.delete` он не касается."""

    def delete(self):
        _refuse_if_history_remains(self.values_list("pk", flat=True))
        return super().delete()


class Apartment(models.Model):
    SINGLE = "single"
    DUAL = "dual"
    METER_CHOICES = [(SINGLE, "Однотарифный"), (DUAL, "День/Ночь")]

    label = models.CharField("Квартира", max_length=200)
    electricity_meter_type = models.CharField(
        "Тип счётчика электроэнергии", max_length=10,
        choices=METER_CHOICES, default=SINGLE)
    has_cold_water = models.BooleanField("Холодная вода", default=True)
    has_hot_water = models.BooleanField("Горячая вода", default=True)
    has_sewage = models.BooleanField("Водоотведение", default=True)
    gvs_heat_norm = models.DecimalField(
        "Норматив подогрева ГВС, Гкал/м³", max_digits=7, decimal_places=5,
        default=Decimal("0"),
        help_text="Тепло на подогрев 1 м³ горячей воды — см. квитанцию УК "
                  "(обычно 0,05–0,065 Гкал/м³). Обязателен, если подведена "
                  "горячая вода: без него подогрев не начислится.")
    round_total = models.BooleanField(
        "Округлять итог", default=True,
        help_text="Итог свыше 10 000 ₽ округляется вниз до кратного 50 ₽ "
                  "(строка «Округление» в квитанции).")
    rent = models.DecimalField("Аренда", max_digits=10, decimal_places=2, default=Decimal("0"))
    internet = models.DecimalField("Интернет", max_digits=10, decimal_places=2, default=Decimal("0"))
    other_fixed = models.DecimalField("Прочее", max_digits=10, decimal_places=2, default=Decimal("0"))

    class Meta:
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

    objects = ApartmentQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        _refuse_if_history_remains([self.pk])
        return super().delete(*args, **kwargs)

    def clean(self):
        """Норматив подогрева обязателен при подведённой горячей воде.

        Дефект №29 гап-анализа: `has_hot_water` по умолчанию `True`, а
        `gvs_heat_norm` — `0`, поэтому только что заведённая квартира начисляла
        за подогрев `0 × ставка = 0` — строка в счёте есть, сумма нулевая,
        ошибки нет. Инвариант принадлежит Properties
        ([ADR-0007]), сюда он попал раньше своего шага C3 по [ADR-0026].

        Проверка держит форму в админке; расчёт прикрыт отдельно
        (`MissingHeatNormError`), потому что `Model.clean` не вызывается при
        `objects.create` и не защитил бы уже заведённые квартиры.
        """
        # `Decimal("0")` ложно, `None` (поле оставили пустым) — тоже.
        if self.has_hot_water and (self.gvs_heat_norm or 0) <= 0:
            raise ValidationError({"gvs_heat_norm": (
                "При подведённой горячей воде норматив подогрева обязателен и "
                "больше нуля. Возьмите его из квитанции управляющей компании "
                "(обычно 0,05–0,065 Гкал/м³). Пока он не задан, подогрев в "
                "счёт не попадает, и вы недополучаете эти деньги."
            )})

    def __str__(self):
        return self.label

class Tenant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="tenant")
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="tenants")
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    # Plan 2 hooks:
    messenger_platform = models.CharField(max_length=10, blank=True)
    messenger_chat_id = models.CharField(max_length=64, blank=True)
    link_code = models.CharField(max_length=32, blank=True)
    # 152-ФЗ: consent must be on file, for the current policy version,
    # before a tenant may connect any OAuth provider (see billing/adapters.py).
    privacy_consent_at = models.DateTimeField(
        "Согласие на обработку ПДн дано", null=True, blank=True)
    privacy_consent_version = models.CharField(
        "Версия политики на момент согласия", max_length=32, blank=True)

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    def __str__(self):
        return self.full_name or self.user.get_username()

# `Tariff` уехал в modules/tariffs/ шагом C1: у него не было ни одного FK и на
# него не ссылалась ни одна модель, поэтому лист графа отделился без разрыва
# связей. Ставки читаются через `modules.tariffs.api.get_rates_on`.

# Meter codes shared by Meter.kind, MeterReading.meter and the calculation core.
METER_KIND_CHOICES = [
    ("cold_water", "Холодная вода"),
    ("hot_water", "Горячая вода"),
    ("electricity_single", "Электроэнергия"),
    ("electricity_day", "Электроэнергия (день)"),
    ("electricity_night", "Электроэнергия (ночь)"),
]

class Meter(models.Model):
    """Физический прибор учёта: номер и показание, зафиксированные в акте
    при подписании договора. Начальное показание — база первого месяца."""
    #: Ссылка идентификатором, без констрейнта (правило 1.3). Прибор
    #: принадлежит Metering, квартира — Properties, и таблицы двух модулей
    #: нельзя разделить, пока их держит внешний ключ.
    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    kind = models.CharField("Вид", max_length=32, choices=METER_KIND_CHOICES)
    serial_number = models.CharField("Заводской номер", max_length=64, blank=True)
    initial_value = models.DecimalField("Начальное показание", max_digits=12, decimal_places=3)
    initial_date = models.DateField("Дата фиксации", null=True, blank=True,
                                    help_text="Дата акта / подписания договора.")

    class Meta:
        verbose_name = "Счётчик"
        verbose_name_plural = "Счётчики"
        unique_together = [("apartment_id", "kind")]

    def __str__(self):
        n = f" № {self.serial_number}" if self.serial_number else ""
        return f"{self.get_kind_display()}{n}"

class MeterReading(models.Model):
    #: Ссылка идентификатором, без констрейнта (правило 1.3). Показание
    #: принадлежит Metering, квартира — Properties.
    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    period = models.DateField("Период")
    meter = models.CharField("Счётчик", max_length=32, choices=METER_KIND_CHOICES)
    value = models.DecimalField("Показание", max_digits=12, decimal_places=3)
    entered_by_tenant = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Показание"
        verbose_name_plural = "Показания"
        unique_together = [("apartment_id", "period", "meter")]
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"кв. {self.apartment_id} {self.period:%Y-%m} {self.meter}={self.value}"

class MonthlyStatement(models.Model):
    UNPAID = "unpaid"; PENDING = "pending"; PAID = "paid"
    STATUS_CHOICES = [(UNPAID, "Не оплачено"), (PENDING, "На проверке"), (PAID, "Оплачено")]

    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="statements")
    period = models.DateField("Период")
    lines = models.JSONField("Строки начисления", default=list)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=UNPAID)

    class Meta:
        verbose_name = "Начисление"
        verbose_name_plural = "Начисления"
        unique_together = [("apartment", "period")]
        ordering = ["-period"]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} — {self.total} ₽"

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
    TELEGRAM = "telegram"; MAX = "max"; WEB = "web"
    SOURCE_CHOICES = [(TELEGRAM, "Telegram"), (MAX, "MAX"), (WEB, "Веб")]
    PENDING = "pending"; CONFIRMED = "confirmed"; REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "На проверке"), (CONFIRMED, "Подтверждён"), (REJECTED, "Отклонён"),
    ]

    statement = models.ForeignKey(MonthlyStatement, on_delete=models.CASCADE,
                                  related_name="payments")
    file = models.FileField("Чек", upload_to=receipt_upload_path)
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
