"""Интерфейсный слой владельца поверх команд модуля.

С шага D1d владелец заселяет и выселяет из панели: добавление — это
`StartTenancy`, проставление даты выезда — `EndTenancy`. С шага D2 здесь же
живёт диалог подтверждения дат: у черновика миграции дата заселения
предложена, а не подтверждена, и владелец либо подтверждает её (действие
списка или сохранение формы), либо исправляет — правка полей формы идёт
командой `CorrectTenancy`.

Отказ команды должен стать ошибкой формы, а не страницей 500. Правил admin
не дублирует (правило 3.6): `clean` прогоняет **тот же домен** — историю
объекта в памяти — и переводит его отказ в подсказку под полем; настоящая
запись всё равно идёт командой.
"""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from .. import api
from ..domain.tenancy import Terms
from .models import Tenancy

ADD_HINT = (
    "Заселение заводит договор: жилец, дата, условия. Повышение ставки потом — "
    "новый договор (завершите этот и заведите следующий), правка полей здесь — "
    "исправление ошибки, счета прошлых месяцев будут помечены к пересмотру."
)


def _terms_of(cleaned) -> Terms:
    return Terms(rent=cleaned["rent"], internet=cleaned["internet"],
                 other_fixed=cleaned["other_fixed"])


class TenancyCommandForm(ModelForm):
    class Meta:
        model = Tenancy
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        try:
            if self.instance.pk is None:
                self._check_start(cleaned)
            else:
                self._check_change(cleaned)
        except (api.PropertyNotFound, api.PeriodOverlap, api.PropertyOutOfService,
                api.EndBeforeStart, api.AlreadyEnded, ValueError) as exc:
            raise ValidationError(str(exc))
        return cleaned

    def _check_start(self, cleaned):
        from modules.properties import api as properties

        from . import repository

        if properties.get_property(cleaned["property_id"]) is None:
            raise api.PropertyNotFound(f"объект #{cleaned['property_id']} не найден")
        from ..domain.tenancy import Tenancy as DomainTenancy

        repository.load_history(cleaned["property_id"]).start(DomainTenancy(
            tenancy_id=None, property_id=cleaned["property_id"],
            account_id=cleaned["account_id"], full_name=cleaned["full_name"],
            started_on=cleaned["started_on"], terms=_terms_of(cleaned)))

    def _check_change(self, cleaned):
        from . import repository

        current = repository.get(self.instance.pk)
        corrected, _ = current.correct(
            started_on=cleaned.get("started_on"),
            full_name=cleaned.get("full_name"), terms=_terms_of(cleaned))
        repository.load_history(current.property_id).correct(corrected)
        if cleaned.get("ended_on") is not None and current.ended_on != cleaned["ended_on"]:
            corrected.end(cleaned["ended_on"])


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    form = TenancyCommandForm
    list_display = ("property_id", "full_name", "account_id", "started_on",
                    "ended_on", "start_confirmed", "rent", "internet", "other_fixed")
    list_filter = ("start_confirmed",)
    search_fields = ("full_name",)
    ordering = ("property_id", "started_on")
    actions = ["confirm_proposed_dates"]

    def get_fieldsets(self, request, obj=None):
        return ((None, {"description": ADD_HINT, "fields": self.get_fields(request, obj)}),)

    def has_delete_permission(self, request, obj=None):
        # Договор — история; выезд фиксируется датой, а не удалением строки.
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ("ended_on", "start_confirmed")   # заселение задаёт остальное
        return ("property_id", "account_id", "start_confirmed")

    def save_model(self, request, obj, form, change):
        """Сохранение идёт командами, а не `obj.save()`, — иначе инварианты и
        события обходятся стороной (тот же урок, что с тарифами на C1a)."""
        if not change:
            obj.pk = api.start_tenancy(
                obj.property_id, obj.account_id, obj.full_name, obj.started_on,
                Terms(rent=obj.rent, internet=obj.internet,
                      other_fixed=obj.other_fixed))
            obj.refresh_from_db()
            return
        corrections = {"started_on", "full_name", "rent", "internet", "other_fixed"}
        if corrections & set(form.changed_data) or not obj.start_confirmed:
            # Сохранение формы черновика подтверждает показанную дату —
            # владелец видел её и не поправил.
            api.correct_tenancy(
                obj.pk, started_on=obj.started_on, full_name=obj.full_name,
                terms=Terms(rent=obj.rent, internet=obj.internet,
                            other_fixed=obj.other_fixed))
        if obj.ended_on is not None and "ended_on" in form.changed_data:
            api.end_tenancy(obj.pk, obj.ended_on)
        obj.refresh_from_db()

    @admin.action(description="Подтвердить предложенную дату заселения")
    def confirm_proposed_dates(self, request, queryset):
        """Диалог шага D2 списком: подтвердить — значит исправить на ту же
        дату. Отказ (дата занята подтверждённым договором — вопрос шага D3)
        не роняет пачку, а называется по каждой строке."""
        confirmed = 0
        for row in queryset.filter(start_confirmed=False):
            try:
                api.correct_tenancy(row.pk, started_on=row.started_on)
                confirmed += 1
            except api.PeriodOverlap as exc:
                self.message_user(
                    request,
                    f"Договор #{row.pk} ({row.full_name}): {exc}. "
                    "Двоих на одну квартиру разведёт следующий шаг.",
                    level="WARNING")
        if confirmed:
            self.message_user(request, f"Дат подтверждено: {confirmed}.")
