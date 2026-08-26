from django.contrib import admin
# Приборы и показания принадлежат Metering (шаг C2c), но их админка осталась
# здесь. Списки показывают квартиру по названию, а название принадлежит
# Properties: обратиться к ней Metering не вправе — он лист графа зависимостей
# (матрица §2 правил). `billing/admin.py` — интерфейсный слой, которому видны
# оба модуля, и до появления отдельного слоя сборки экранов место админки
# здесь. Регистрация показаний вдобавок пересчитывает счёт; это уйдёт на C2f,
# когда Billing начнёт слушать событие.
from django.contrib import messages
from django.utils.html import format_html
from modules.metering import api as metering
from modules.metering.infrastructure.models import (
    Meter, MeterReading, PeriodLock,
)
from .models import (
    Apartment, Tenant, MonthlyStatement, Document, Payment,
)
from .services.statements import generate_statement, missing_meters
from .services.intake import confirm_payment, reject_payment, _revert_if_no_pending

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("label", "meters_to_register", "electricity_meter_type",
                    "rent", "internet")
    list_filter = ("electricity_meter_type",)
    search_fields = ("label",)

    @admin.display(description="Не заведены приборы")
    def meters_to_register(self, obj):
        """Услуги, обещанные флагами квартиры, но без прибора в реестре.

        С шага C2e состав начисляемого задаёт реестр, и расчёт из-за
        незаведённого прибора не останавливается — ответственность за состав
        несёт владелец. Но счёт без горячей воды выглядит законным и
        недоначисляет незаметно, поэтому расхождение видно здесь, а не только
        в момент пересчёта: счёт чаще всего порождает жилец, сдавая показания,
        и сообщения того пересчёта владелец не увидит никогда.
        """
        missing = missing_meters(obj)
        if not missing:
            return "—"
        names = metering.resources()
        return format_html(
            '<span style="color:#b32d2e">{}</span>',
            ", ".join(names.get(code, code) for code in missing))
    # `MeterInline` убран на шаге C2a3: вложенная форма требует внешнего
    # ключа, а его больше нет. Приборы получили собственный раздел ниже и
    # уедут в Metering вместе с моделью на C2c.


@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    list_display = ("apartment_label", "resource", "serial_number",
                    "initial_value", "initial_date")
    list_filter = ("resource",)

    @admin.display(description="Квартира", ordering="apartment_id")
    def apartment_label(self, obj):
        """Название квартиры по идентификатору.

        Раньше его показывала связь модели. Теперь это отдельный запрос —
        и в этом весь смысл разрыва: данные двух модулей больше не сшиты
        соединением таблиц, а собираются тем, кто их показывает.
        """
        apartment = Apartment.objects.filter(pk=obj.apartment_id).first()
        return apartment.label if apartment else f"— (id {obj.apartment_id})"

    def save_model(self, request, obj, form, change):
        """Ввод прибора в учёт идёт командой, а не `obj.save()`.

        Иначе объявленное на C2f событие `MeterRegistered` не наступало бы
        никогда: админка — единственный способ завести прибор. Тот же урок,
        что с тарифами на C1a.

        Правка уже заведённого прибора (номер, дата акта) остаётся обычным
        сохранением: команды на это в спецификации нет, а замена счётчика —
        отдельная операция со своим смыслом, и она отложена (P2).
        """
        if change:
            super().save_model(request, obj, form, change)
            return
        metering.register_meter(
            apartment_id=obj.apartment_id, resource=obj.resource,
            initial_value=obj.initial_value, serial_number=obj.serial_number,
            initial_date=obj.initial_date)
        self._adopt_written_row(obj)

    @staticmethod
    def _adopt_written_row(obj):
        """Подставить в форму ключ строки, которую записала команда.

        Объект формы командой не сохранялся и ключа не имеет; админке он нужен,
        чтобы построить ссылку «изменить» и сообщение об успехе.
        """
        written = (Meter.objects
                   .filter(apartment_id=obj.apartment_id, resource=obj.resource)
                   .order_by("-pk").first())
        if written is not None:
            obj.pk = written.pk

@admin.register(PeriodLock)
class PeriodLockAdmin(admin.ModelAdmin):
    """Закрытые периоды — и способ снять замок.

    Требование 3 [ADR-0012](../docs/architecture/adr/0012-metering-period-lock.md):
    у владельца должен быть доступный способ снять замок, иначе первая же
    опечатка в показаниях превращается в тупик. Снятие идёт командой модуля, а
    не удалением строки: иначе `MeteringPeriodReopened` не наступит, а след
    ручного вмешательства в закрытый месяц нужен независимо от того, слушает ли
    его сегодня кто-нибудь.

    Заводить замок отсюда нельзя: его ставит Billing, выставляя счёт. Ручное
    закрытие периода было бы решением без документа, из-за которого оно
    принимается.
    """

    list_display = ("apartment_label", "period", "closed_at")
    date_hierarchy = "period"

    @admin.display(description="Квартира", ordering="apartment_id")
    def apartment_label(self, obj):
        apartment = Apartment.objects.filter(pk=obj.apartment_id).first()
        return apartment.label if apartment else f"— (id {obj.apartment_id})"

    def has_add_permission(self, request):
        return False

    def delete_model(self, request, obj):
        metering.reopen_period(obj.apartment_id, obj.period)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            metering.reopen_period(obj.apartment_id, obj.period)


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "apartment")
    search_fields = ("full_name", "user__username")
    inlines = [DocumentInline]

# TariffAdmin уехал в modules/tariffs/infrastructure/admin.py шагом C1 и там
# переписан: он ходит через команды модуля, а не правит таблицу напрямую.

@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("apartment_label", "period", "resource", "value",
                    "entered_by_tenant")
    list_filter = ("resource",)
    date_hierarchy = "period"

    @admin.display(description="Квартира", ordering="apartment_id")
    def apartment_label(self, obj):
        apartment = Apartment.objects.filter(pk=obj.apartment_id).first()
        return apartment.label if apartment else f"— (id {obj.apartment_id})"

    def save_model(self, request, obj, form, change):
        """Сдача и исправление — разные операции с разными событиями.

        Форма различает их по тому, редактируется ли запись: новая строка —
        сдача показания, правка существующей — исправление ошибки. Смысл тот
        же, что у Tariffs между публикацией и исправлением версии.
        """
        if change:
            metering.correct_reading(obj.apartment_id, obj.period,
                                     obj.resource, obj.value)
        else:
            metering.submit_readings(obj.apartment_id, obj.period,
                                     {obj.resource: obj.value},
                                     entered_by_tenant=obj.entered_by_tenant)
        _adopt_reading_row(obj)
        try:
            apartment = Apartment.objects.get(pk=obj.apartment_id)
            generate_statement(apartment, obj.period)
            self.message_user(request, "Начисление за период пересчитано.")
            _warn_about_missing_meters(self, request, apartment)
        except Exception as exc:
            self.message_user(
                request,
                f"Показание сохранено, но начисление не пересчитано: {exc}",
                level=messages.WARNING)

def _warn_about_missing_meters(modeladmin, request, apartment):
    """Сказать владельцу, каких приборов не хватает, — при каждом пересчёте.

    Дублирует столбец в списке квартир намеренно: в списке предупреждение
    видно всегда, здесь — в тот момент, когда владелец смотрит на счёт и может
    сверить сумму с квитанцией.
    """
    missing = missing_meters(apartment)
    if not missing:
        return
    names = metering.resources()
    modeladmin.message_user(
        request,
        f"У квартиры «{apartment.label}» не заведены приборы: "
        + ", ".join(names.get(code, code) for code in missing)
        + ". Эти услуги в счёт не попали.",
        level=messages.WARNING)


def _adopt_reading_row(obj):
    written = (MeterReading.objects
               .filter(apartment_id=obj.apartment_id, period=obj.period,
                       resource=obj.resource)
               .order_by("-pk").first())
    if written is not None:
        obj.pk = written.pk


@admin.action(description="Пересчитать начисления")
def regenerate_statements(modeladmin, request, queryset):
    ok = 0
    for stmt in queryset:
        try:
            generate_statement(stmt.apartment, stmt.period)
            ok += 1
            _warn_about_missing_meters(modeladmin, request, stmt.apartment)
        except Exception as exc:  # report per-statement failure, don't abort the batch
            modeladmin.message_user(
                request,
                f"Ошибка пересчёта ({stmt.apartment} {stmt.period:%Y-%m}): {exc}",
                level=messages.ERROR,
            )
    if ok:
        modeladmin.message_user(request, f"Пересчитано начислений: {ok}.")

@admin.action(description="Подтвердить оплату")
def confirm_payments(modeladmin, request, queryset):
    n = 0
    for p in queryset.filter(status=Payment.PENDING):
        confirm_payment(p); n += 1
    modeladmin.message_user(request, f"Подтверждено платежей: {n}.")

@admin.action(description="Отклонить платёж")
def reject_payments(modeladmin, request, queryset):
    n = 0
    for p in queryset.filter(status=Payment.PENDING):
        reject_payment(p); n += 1
    modeladmin.message_user(request, f"Отклонено платежей: {n}.", level=messages.WARNING)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("statement", "source", "status", "submitted_at", "preview")
    list_filter = ("status", "source")
    date_hierarchy = "submitted_at"
    readonly_fields = ("preview", "submitted_at")
    actions = [confirm_payments, reject_payments]

    @admin.display(description="Чек")
    def preview(self, obj):
        if not obj.file:
            return "—"
        url = obj.file.url
        if url.lower().endswith(".pdf"):
            return format_html('<a href="{}" target="_blank">PDF-чек</a>', url)
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-height:120px"></a>', url, url)

    def _delete_with_file(self, payment):
        payment.file.delete(save=False)
        stmt = payment.statement
        payment.delete()
        _revert_if_no_pending(stmt)

    def delete_model(self, request, obj):
        self._delete_with_file(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._delete_with_file(obj)

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("source", "status", "submitted_at")

@admin.register(MonthlyStatement)
class MonthlyStatementAdmin(admin.ModelAdmin):
    list_display = ("apartment", "period", "total", "status")
    list_filter = ("status", "apartment")
    date_hierarchy = "period"
    actions = [regenerate_statements]
    inlines = [PaymentInline]

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "uploaded_at")
