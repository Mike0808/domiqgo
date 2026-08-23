from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import (
    Apartment, Meter, Tenant, MeterReading, MonthlyStatement, Document, Payment,
)
from .services.statements import generate_statement
from .services.intake import confirm_payment, reject_payment, _revert_if_no_pending

class MeterInline(admin.TabularInline):
    model = Meter
    extra = 0

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("label", "electricity_meter_type", "rent", "internet")
    list_filter = ("electricity_meter_type",)
    search_fields = ("label",)
    inlines = [MeterInline]

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
    list_display = ("apartment", "period", "meter", "value", "entered_by_tenant")
    list_filter = ("meter", "apartment")
    date_hierarchy = "period"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            generate_statement(obj.apartment, obj.period)
            self.message_user(request, "Начисление за период пересчитано.")
        except Exception as exc:
            self.message_user(
                request,
                f"Показание сохранено, но начисление не пересчитано: {exc}",
                level=messages.WARNING)

@admin.action(description="Пересчитать начисления")
def regenerate_statements(modeladmin, request, queryset):
    ok = 0
    for stmt in queryset:
        try:
            generate_statement(stmt.apartment, stmt.period)
            ok += 1
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
