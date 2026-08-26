from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError
from django.utils import timezone

class PropertyNotDeletable(ProtectedError):
    """Объект недвижимости не удаляют — его выводят из эксплуатации.

    Шаг C3a. Прежде удаление отклонялось выборочно: сначала каскадом
    `PROTECT` (дефект №9), затем — после разрыва связей на C2 — явной
    проверкой, спрашивавшей Metering, есть ли за квартирой приборы и
    показания. Пустую квартиру при этом удалить было можно.

    Теперь удаления нет как операции. Причины две, и обе перевешивают удобство
    исправления опечатки:

    1. **Проверять больше нечем.** Ссылки между модулями — идентификаторы без
       констрейнтов, каскада между таблицами разных модулей не существует по
       определению, а спрашивать Metering из Properties запрещено: тот лист
       графа зависимостей. Выборочный запрет требовал бы обхода всех модулей
       системы — то есть ровно того, ради отмены чего связи и рвались.
    2. **Объект живёт десятилетиями.** Проданная квартира не исчезает из
       истории: по ней остаются выставленные счета, показания и договоры, и
       отчёт за прошлый год обязан их показать. «Удалить» — неверное слово для
       того, что владелец на самом деле делает.

    Опечатку в списке объектов исправляет вывод из эксплуатации: выведенный
    объект не показывается в обычном списке и не участвует в начислениях
    ([ADR-0009](../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md)).
    """

    def __init__(self):
        super().__init__(
            "Объект недвижимости не удаляется: по нему остаются счета, "
            "показания и договоры. Выведите его из эксплуатации — он исчезнет "
            "из списка действующих, а история останется.",
            set())


class ApartmentQuerySet(models.QuerySet):
    """Удаление списком — тот путь, которым удаляет админка, выделив объекты
    галочками. Переопределения `Model.delete` он не касается."""

    def delete(self):
        raise PropertyNotDeletable()


class Apartment(models.Model):
    SINGLE = "single"
    DUAL = "dual"
    METER_CHOICES = [(SINGLE, "Однотарифный"), (DUAL, "День/Ночь")]

    label = models.CharField("Квартира", max_length=200)
    #: Дата вывода из эксплуатации; `None` — объект действует. Датой, а не
    #: флагом: владельцу важно, с какого числа объект перестал сдаваться, а
    #: отчёту за прошлый год — что тогда он ещё сдавался.
    decommissioned_on = models.DateField(
        "Выведен из эксплуатации", null=True, blank=True,
        help_text="Пусто — объект в эксплуатации.")
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
        raise PropertyNotDeletable()

    def decommission(self, on_date=None):
        """Вывести объект из эксплуатации: продан, больше не сдаётся.

        Действующий договор при этом **не прекращается**
        ([ADR-0009](../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md)):
        договор — юридический факт, и система не вправе отменять его из-за
        административной отметки. Предупредить, что в объекте живёт жилец,
        обязан прикладной слой, у которого есть обе стороны.
        """
        self.decommissioned_on = on_date or timezone.localdate()
        self.save(update_fields=["decommissioned_on"])

    def recommission(self):
        """Вернуть объект в эксплуатацию."""
        self.decommissioned_on = None
        self.save(update_fields=["decommissioned_on"])

    @property
    def in_service(self) -> bool:
        return self.decommissioned_on is None

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

# `METER_KIND_CHOICES`, `Meter` и `MeterReading` уехали в
# `modules/metering/` шагом C2c плана миграции. Таблицы переименованы в
# `metering_meter` и `metering_reading`; словарь стал каталогом видов ресурса
# `modules/metering/domain/catalogue.py`. Читать их отсюда следует только
# через `modules.metering.api`.

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
