"""Хранение объектов недвижимости. Единственное место модуля, знающее о базе.

Таблица переехала из `billing/` шагом C3b через `SeparateDatabaseAndState`:
данные остались на месте, сменился владелец.

**Временные жильцы.** В таблице лежат поля, которые Properties не принадлежат:
`rent`, `internet`, `other_fixed` — условия договора и ждут Tenancy;
`round_total` — политика оформления документа и ждёт Billing;
`electricity_meter_type` — свойство прибора и уезжает в Metering шагом C3d.
Вырезать их одним движением нельзя: у каждого свой владелец и свой шаг плана,
а до тех пор на них опирается расчёт счёта.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError


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
    ([ADR-0009](../../../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md)).
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
        db_table = "properties_apartment"
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

    objects = ApartmentQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        raise PropertyNotDeletable()

    @property
    def in_service(self) -> bool:
        """Читаемая форма того же, что говорит домен.

        Не правило, а зеркало поля: вывод из эксплуатации и возврат — команды
        модуля, и меняют состояние они, а не эта строка.
        """
        return self.decommissioned_on is None

    def clean(self):
        """Норматив подогрева обязателен при подведённой горячей воде.

        Дефект №29 гап-анализа: `has_hot_water` по умолчанию `True`, а
        `gvs_heat_norm` — `0`, поэтому только что заведённая квартира начисляла
        за подогрев `0 × ставка = 0` — строка в счёте есть, сумма нулевая,
        ошибки нет. Инвариант принадлежит Properties
        (ADR-0007). Здесь он остался после переезда C3b; в домен модуля
        переезжает шагом C3c.

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
