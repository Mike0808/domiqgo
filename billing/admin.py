from django.contrib import admin
from .models import (
    Apartment, Tenant, Tariff, MeterReading, MonthlyStatement, Document,
)
from .services.statements import generate_statement

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("label", "electricity_meter_type", "rent", "internet")
    list_filter = ("electricity_meter_type",)
    search_fields = ("label",)

class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "apartment")
    search_fields = ("full_name", "user__username")
    inlines = [DocumentInline]

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("utility_type", "rate", "effective_from", "source_name")
    list_filter = ("utility_type",)
    ordering = ("utility_type", "-effective_from")

@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("apartment", "period", "meter", "value", "entered_by_tenant")
    list_filter = ("meter", "apartment")
    date_hierarchy = "period"

@admin.action(description="Пересчитать начисления")
def regenerate_statements(modeladmin, request, queryset):
    for stmt in queryset:
        generate_statement(stmt.apartment, stmt.period)

@admin.register(MonthlyStatement)
class MonthlyStatementAdmin(admin.ModelAdmin):
    list_display = ("apartment", "period", "total", "status")
    list_filter = ("status", "apartment")
    date_hierarchy = "period"
    actions = [regenerate_statements]

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "uploaded_at")
