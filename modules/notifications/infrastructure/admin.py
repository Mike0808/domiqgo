"""Интерфейсный слой владельца: журнал сообщений и прогонов (шаг F2).

Сообщение — свидетельство доставки: руками его не правят (только повторная
отправка недоставленного и снятие неотправленного — командами). Правило 3.6
соблюдено: здесь нет ни одного условия о домене — только перевод действий в
команды и предупреждение о молчащем прогоне.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.utils import timezone

from .. import api
from .models import Channel, DispatchRun, OutgoingMessage


class ChannelCommandForm(ModelForm):
    class Meta:
        model = Channel
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        # Отказ команды — ошибка формы, а не страница 500 (приём D1d): чужой
        # адрес не перепривязывается молча (инвариант 2).
        existing = Channel.objects.filter(platform=cleaned["platform"],
                                          address=cleaned["address"]).first()
        if existing is not None and existing.account_id != cleaned["account_id"]:
            raise ValidationError(
                "Этот адрес уже привязан к другой учётной записи — сначала "
                "отвяжите его там.")
        return cleaned


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    """Каналы доставки. Мессенджер жилец привязывает сам кодом через бота;
    почту (шаг F4) заводит владелец здесь — адрес учётной записи Identity
    служит лишь подсказкой (ADR-0018), доставка на него не смотрит.

    Правка запрещена: адрес меняют перепривязкой, чтобы отказ «чужой адрес»
    не обходился формой.
    """

    form = ChannelCommandForm
    list_display = ("account_id", "platform", "address")
    list_filter = ("platform",)

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        api.bind_channel(obj.account_id, obj.platform, obj.address)
        obj.pk = Channel.objects.get(account_id=obj.account_id,
                                     platform=obj.platform).pk
        obj.refresh_from_db()

    def delete_model(self, request, obj):
        api.unbind_channel(obj.account_id, obj.platform)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            api.unbind_channel(obj.account_id, obj.platform)


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
