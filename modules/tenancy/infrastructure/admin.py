"""Интерфейсный слой владельца поверх команд модуля.

С шага D1d владелец заселяет и выселяет из панели: добавление — это
`StartTenancy`, проставление даты выезда — `EndTenancy`. Ничего другого форма
не правит: условия внутри договора неизменны (инвариант 3), а исправление
ошибочных сведений — `CorrectTenancy` — приходит вместе с диалогом
подтверждения дат (шаг D2). Дата заселения черновика до тех пор честно
показывается неподтверждённой.

Отказ команды должен стать ошибкой формы, а не страницей 500. Правил admin
не дублирует (правило 3.6): `clean` прогоняет **тот же домен** — историю
объекта в памяти — и переводит его отказ в подсказку под полем; настоящая
запись всё равно идёт командой.
"""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from .. import api
from ..domain.tenancy import Tenancy as DomainTenancy, Terms
from .models import Tenancy

ADD_HINT = (
    "Заселение заводит договор: жилец, дата, условия. Изменение условий потом — "
    "это новый договор, а не правка этого. У существующего договора правится "
    "только дата выезда."
)


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
            elif cleaned.get("ended_on") is not None:
                self._check_end(cleaned)
        except (api.PropertyNotFound, api.PeriodOverlap, api.PropertyOutOfService,
                api.EndBeforeStart, api.AlreadyEnded, ValueError) as exc:
            raise ValidationError(str(exc))
        return cleaned

    def _check_start(self, cleaned):
        from modules.properties import api as properties

        from . import repository

        if properties.get_property(cleaned["property_id"]) is None:
            raise api.PropertyNotFound(f"объект #{cleaned['property_id']} не найден")
        history = repository.load_history(cleaned["property_id"])
        history.start(DomainTenancy(
            tenancy_id=None, property_id=cleaned["property_id"],
            account_id=cleaned["account_id"], full_name=cleaned["full_name"],
            started_on=cleaned["started_on"],
            terms=Terms(rent=cleaned["rent"], internet=cleaned["internet"],
                        other_fixed=cleaned["other_fixed"])))

    def _check_end(self, cleaned):
        from . import repository

        current = repository.get(self.instance.pk)
        if current.ended_on != cleaned["ended_on"]:
            current.end(cleaned["ended_on"])


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    form = TenancyCommandForm
    list_display = ("property_id", "full_name", "account_id", "started_on",
                    "ended_on", "start_confirmed", "rent", "internet", "other_fixed")
    list_filter = ("start_confirmed",)
    search_fields = ("full_name",)
    ordering = ("property_id", "started_on")

    def get_fieldsets(self, request, obj=None):
        return ((None, {"description": ADD_HINT, "fields": self.get_fields(request, obj)}),)

    def has_delete_permission(self, request, obj=None):
        # Договор — история; выезд фиксируется датой, а не удалением строки.
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ("ended_on", "start_confirmed")   # заселение задаёт остальное
        # Существующий договор: изменить можно только дату выезда (EndTenancy).
        return ("property_id", "account_id", "full_name", "started_on",
                "start_confirmed", "rent", "internet", "other_fixed")

    def save_model(self, request, obj, form, change):
        """Сохранение идёт командой, а не `obj.save()`, — иначе инварианты и
        события обходятся стороной (тот же урок, что с тарифами на C1a)."""
        if not change:
            obj.pk = api.start_tenancy(
                obj.property_id, obj.account_id, obj.full_name, obj.started_on,
                Terms(rent=obj.rent, internet=obj.internet,
                      other_fixed=obj.other_fixed))
        elif obj.ended_on is not None and "ended_on" in form.changed_data:
            api.end_tenancy(obj.pk, obj.ended_on)
        obj.refresh_from_db()
