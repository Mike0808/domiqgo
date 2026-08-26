"""Точка учёта — корень агрегата Metering.

Корень — **точка**, а не отдельный прибор: правила охватывают приборы вместе.
База отсчёта одного прибора выводится из его же истории, но комплектность и
замок периода (шаг C2g) многоприборные, и объект, видящий один прибор, их
проверить не может. Это подтверждается и работающим кодом: сдача показаний уже
сегодня идёт одной транзакцией на все приборы квартиры.

*Отвергнуто:* корень — показание, как было в as-is (`MeterReading` —
самостоятельная модель). Именно это и привело к тому, что правило
монотонности физически не могло жить рядом с данными и оказалось внутри
калькулятора счёта (`billing/services/calculation.py`), то есть в чужом
модуле.

Здесь только stdlib. Ни Django, ни базы: точку можно собрать из списков и
спросить у неё расход, не поднимая ничего.
"""

from dataclasses import dataclass
from decimal import Decimal


class ReadingWentBackwards(ValueError):
    """Показание меньше базы отсчёта.

    Счётчик не отматывается назад: значение меньше прежнего означает либо
    опечатку, либо замену прибора. Ни то ни другое нельзя истолковать за
    владельца — отрицательный расход уменьшил бы счёт, а нулевой скрыл бы
    ошибку.
    """


class BaselineMissing(LookupError):
    """У части ресурсов нет ни предыдущего показания, ни начального значения.

    Считать от неявного нуля нельзя: расход вышел бы равным всему показанию
    прибора, и жилец заплатил бы за годы до себя. Как поступить, решает
    вызывающий: сегодня Billing превращает это в отказ считать счёт.
    """

    def __init__(self, resources):
        self.resources = list(resources)
        super().__init__("Нет базы отсчёта для: " + ", ".join(self.resources))


@dataclass(frozen=True)
class Consumption:
    """Расход за период вместе с обеими границами интервала.

    Границы едут наружу не для красоты: счёт обязан их напечатать — жилец
    должен видеть, из чего получилась цифра. Вычитает при этом Metering, а не
    Billing: при замене прибора вычитание перестаёт быть простой разностью, и
    знать об этом должен владелец прибора.
    """

    resource: str
    baseline: Decimal
    current: Decimal
    used: Decimal


class MeteringPoint:
    """Приборы точки учёта и показания вокруг одного периода.

    Собирается на период, а не на всю историю: расход считается от предыдущего
    показания, и остальные годы для ответа не нужны. Полная история —
    отдельный вопрос (выгрузка в Reporting), и грузить её ради каждого счёта
    значило бы вычитывать всю жизнь квартиры двенадцать раз в год.
    """

    def __init__(self, apartment_id: int, initial_values: dict[str, Decimal],
                 previous_values: dict[str, Decimal],
                 current_values: dict[str, Decimal]):
        self.apartment_id = apartment_id
        self._initial = dict(initial_values)
        self._previous = dict(previous_values)
        self._current = dict(current_values)

    def baseline_for(self, resource: str) -> Decimal | None:
        """Показание предыдущего периода, иначе начальное значение прибора.

        Начальное значение — то, что зафиксировано актом при подписании
        договора. Порядок именно такой: показание за прошлый месяц точнее
        акта двухлетней давности.
        """
        if resource in self._previous:
            return self._previous[resource]
        return self._initial.get(resource)

    def consumption(self, resources) -> dict[str, Consumption]:
        """Расход по каждому запрошенному ресурсу.

        Сначала проверяются все базы отсчёта и только потом считается расход:
        отсутствие базы — беда всей точки, и сообщать о ней надо целиком, а не
        по одному ресурсу за прогон.
        """
        resources = list(resources)
        without_baseline = [r for r in resources if self.baseline_for(r) is None]
        if without_baseline:
            raise BaselineMissing(without_baseline)

        result = {}
        for resource in resources:
            baseline = self.baseline_for(resource)
            current = self._current[resource]
            used = current - baseline
            if used < 0:
                raise ReadingWentBackwards(
                    f"Показание по счётчику «{resource}» уменьшилось: "
                    f"{baseline} -> {current}")
            result[resource] = Consumption(resource=resource, baseline=baseline,
                                           current=current, used=used)
        return result
