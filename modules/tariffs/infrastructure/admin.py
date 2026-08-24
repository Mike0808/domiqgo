"""Интерфейсный слой владельца поверх команд модуля.

В as-is это был обычный `ModelAdmin` по таблице. Переписан не ради чистоты:
через прямой CRUD инвариант агрегата обходится, а события не публикуются
вовсе — а админка сегодня единственный способ завести ставку. То есть без этой
правки шаг C1 объявил бы события, которые не наступают никогда.

Правило 3.6 («бизнес-правила не живут в admin») соблюдено: здесь нет ни одного
условия и ни одного расчёта — только перевод формы в вызов команды.
"""

from django.contrib import admin

from ..api import (
    correct_tariff_version, publish_tariff_version, withdraw_tariff_version,
)
from .models import TariffVersion


#: Различение «новая версия» и «правка версии» — смысловое, и до сих пор оно
#: жило в коде, спецификации и журнале, то есть везде, кроме того места, где
#: решение принимает владелец. Кнопки админки называются «Добавить» и
#: «Изменить» и о разнице молчат. Текст ниже — не правило (правило 3.6), а
#: перевод уже принятого решения на язык того, кто нажимает кнопку.
ADD_HINT = (
    "Новая версия — это изменение цены. Прежняя продолжает действовать в своём "
    "прошлом: перерасчёт за прошедший период возьмёт ту ставку, что была тогда."
)
CHANGE_HINT = (
    "Правка исправляет ошибку ввода: новой версии не появится, изменится эта. "
    "Чтобы записать изменение цены, вернитесь к списку и добавьте новую версию "
    "с новой датой."
)


@admin.register(TariffVersion)
class TariffVersionAdmin(admin.ModelAdmin):
    list_display = ("utility", "rate", "effective_from", "source_name")
    list_filter = ("utility",)
    ordering = ("utility", "-effective_from")

    def get_fieldsets(self, request, obj=None):
        return ((None, {
            "description": CHANGE_HINT if obj else ADD_HINT,
            "fields": ("utility", "rate", "effective_from",
                       "source_name", "source_url"),
        }),)

    def get_readonly_fields(self, request, obj=None):
        """Услугу у заведённой версии не меняют.

        Смена услуги — это не правка версии, а перенос между тарифными
        линиями, то есть отзыв в одной и публикация в другой. Команды такой
        операции нет, и заводить её ради опечатки в выпадающем списке
        незачем: отозвать и завести заново — две кнопки, которые уже есть.
        """
        return ("utility",) if obj else ()

    def save_model(self, request, obj, form, change):
        """Сохранение идёт командой, а не `obj.save()`.

        Различение принципиально: новая ставка — исторический факт (регулятор
        поднял цену), правка существующей — признание ошибки оператора. Они
        по-разному влияют на уже выставленные счета и порождают разные
        события. Форма различает их по тому, редактируется ли запись.
        """
        if change:
            correct_tariff_version(
                utility=obj.utility,
                was_effective_from=form.initial["effective_from"],
                rate=obj.rate,
                effective_from=obj.effective_from,
                source_name=obj.source_name,
                source_url=obj.source_url,
            )
        else:
            publish_tariff_version(
                utility=obj.utility, rate=obj.rate,
                effective_from=obj.effective_from,
                source_name=obj.source_name, source_url=obj.source_url,
            )
        self._adopt_written_row(obj)

    def delete_model(self, request, obj):
        withdraw_tariff_version(utility=obj.utility,
                                effective_from=obj.effective_from)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            withdraw_tariff_version(utility=obj.utility,
                                    effective_from=obj.effective_from)

    @staticmethod
    def _adopt_written_row(obj):
        """Подставить в форму ключ строки, которую записала команда.

        Репозиторий перезаписывает линию целиком, поэтому первичный ключ после
        сохранения другой. Админке он нужен, чтобы построить ссылку «изменить»
        и сообщение об успехе; без этого добавление уходит в ошибку на
        совершенно исправной операции.
        """
        written = (TariffVersion.objects
                   .filter(utility=obj.utility, effective_from=obj.effective_from)
                   .order_by("-pk").first())
        if written is not None:
            obj.pk = written.pk
