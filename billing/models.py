from decimal import Decimal
from django.conf import settings
from django.db import models

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
                  "(обычно 0,05–0,065 Гкал/м³).")
    rent = models.DecimalField("Аренда", max_digits=10, decimal_places=2, default=Decimal("0"))
    internet = models.DecimalField("Интернет", max_digits=10, decimal_places=2, default=Decimal("0"))
    other_fixed = models.DecimalField("Прочее", max_digits=10, decimal_places=2, default=Decimal("0"))

    class Meta:
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

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

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    def __str__(self):
        return self.full_name or self.user.get_username()

class Tariff(models.Model):
    COLD = "cold_water"; SEWAGE = "sewage"
    # ГВС в Уфе двухкомпонентный: объём (₽/м³) + подогрев (₽/Гкал).
    HOT_COLD = "hot_water_cold_component"; HOT_HEAT = "hot_water_heat_component"
    ESINGLE = "electricity_single"; EDAY = "electricity_day"; ENIGHT = "electricity_night"
    UTILITY_CHOICES = [
        (COLD, "Холодная вода"),
        (HOT_COLD, "ГВС — компонент на холодную воду"),
        (HOT_HEAT, "ГВС — компонент на тепловую энергию"),
        (SEWAGE, "Водоотведение"),
        (ESINGLE, "Электроэнергия"), (EDAY, "Электроэнергия (день)"),
        (ENIGHT, "Электроэнергия (ночь)"),
    ]
    utility_type = models.CharField("Услуга", max_length=32, choices=UTILITY_CHOICES)
    rate = models.DecimalField("Тариф, ₽/ед.", max_digits=10, decimal_places=4)
    effective_from = models.DateField("Действует с")
    source_name = models.CharField("Источник", max_length=200, blank=True)
    source_url = models.URLField("Ссылка на источник", blank=True)

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        ordering = ["utility_type", "-effective_from"]

    def __str__(self):
        return f"{self.get_utility_type_display()} — {self.rate} (с {self.effective_from})"

class MeterReading(models.Model):
    apartment = models.ForeignKey(Apartment, on_delete=models.CASCADE, related_name="readings")
    period = models.DateField("Период")
    meter = models.CharField("Счётчик", max_length=32)
    value = models.DecimalField("Показание", max_digits=12, decimal_places=3)
    entered_by_tenant = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Показание"
        verbose_name_plural = "Показания"
        unique_together = [("apartment", "period", "meter")]
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} {self.meter}={self.value}"

class MonthlyStatement(models.Model):
    UNPAID = "unpaid"; PENDING = "pending"; PAID = "paid"
    STATUS_CHOICES = [(UNPAID, "Не оплачено"), (PENDING, "На проверке"), (PAID, "Оплачено")]

    apartment = models.ForeignKey(Apartment, on_delete=models.CASCADE, related_name="statements")
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
