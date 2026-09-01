"""Интерфейсный слой владельца: договоры — пока только для чтения.

С шага D1b условия договора живут здесь, а не в карточке квартиры, и владелец
должен их видеть. Править их этой формой нельзя: условия внутри договора
неизменны (инвариант 3), а изменение условий — это `RenewTenancy` или
`CorrectTenancy`, и обе команды приходят вместе с диалогом подтверждения дат
(шаг D2). До тех пор список честно показывает, что дата у черновика не
подтверждена.

Правило 3.6 («бизнес-правила не живут в admin») соблюдено: здесь нет ни
одного условия — только отображение.
"""

from django.contrib import admin

from .models import Tenancy


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    list_display = ("property_id", "full_name", "account_id", "started_on",
                    "ended_on", "start_confirmed", "rent", "internet", "other_fixed")
    list_filter = ("start_confirmed",)
    search_fields = ("full_name",)
    ordering = ("property_id", "started_on")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
