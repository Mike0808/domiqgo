"""Интерфейсный слой владельца: журнал сообщений и прогонов (шаг F2).

Сообщение — свидетельство доставки: руками его не правят (только повторная
отправка недоставленного и снятие неотправленного — командами). Правило 3.6
соблюдено: здесь нет ни одного условия о домене — только перевод действий в
команды и предупреждение о молчащем прогоне.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from .. import api
from .models import DispatchRun, OutgoingMessage


@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(admin.ModelAdmin):
    list_display = ("queued_at", "account_id", "platform", "state",
                    "attempts", "last_error", "text")
    list_filter = ("state", "platform")
    actions = ["dispatch_now", "resend", "cancel"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Наблюдаемость (план этапа F): несостоявшийся прогон — тишина, и
        тишину надо показывать. Очередь, которую час никто не разбирал, —
        признак того, что прогон по расписанию не работает."""
        stale = OutgoingMessage.objects.filter(
            state="queued",
            queued_at__lt=timezone.now() - timedelta(hours=1)).count()
        if stale and request.method == "GET":
            self.message_user(
                request,
                f"В очереди {stale} сообщений старше часа — похоже, прогон "
                "отправки не запускается. Проверьте расписание "
                "(dispatch_notifications) или отправьте очередь сейчас.",
                level=messages.ERROR)
        return super().changelist_view(request, extra_context)

    @admin.action(description="Отправить очередь сейчас")
    def dispatch_now(self, request, queryset):
        sent, failed = api.dispatch_pending()
        self.message_user(request,
                          f"Доставлено: {sent}; не доставлено навсегда: {failed}.")

    @admin.action(description="Отправить повторно (недоставленные)")
    def resend(self, request, queryset):
        for row in queryset:
            try:
                api.resend_message(row.pk)
            except Exception as exc:
                self.message_user(request, f"#{row.pk}: {exc}",
                                  level=messages.ERROR)

    @admin.action(description="Снять с очереди (неотправленные)")
    def cancel(self, request, queryset):
        for row in queryset:
            try:
                api.cancel_pending(row.pk)
            except Exception as exc:
                self.message_user(request, f"#{row.pk}: {exc}",
                                  level=messages.ERROR)


@admin.register(DispatchRun)
class DispatchRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "sent", "failed")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
