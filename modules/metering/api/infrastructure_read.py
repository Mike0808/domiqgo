"""Чтение истории показаний для read-контракта Reporting (шаг G2).

Файл лежит рядом с `api/__init__`, а не в нём: импорт моделей до готовности
Django ломает загрузку — тот же приём, что `_repository()`.
"""


def list_readings(apartment_id: int) -> list[dict]:
    from ..infrastructure.models import MeterReading

    return [{
        "period": row.period, "resource": row.resource, "value": row.value,
        "entered_by_tenant": row.entered_by_tenant,
    } for row in (MeterReading.objects.filter(apartment_id=apartment_id)
                  .order_by("period", "resource"))]
