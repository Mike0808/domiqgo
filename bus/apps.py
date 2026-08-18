from django.apps import AppConfig


class BusConfig(AppConfig):
    """Шина становится Django-приложением на шаге B2 — ради журнала.

    На B1 приложения не было и не требовалось: транспорту база не нужна. Метка
    `bus` совпадает с именем пакета, поэтому таблица журнала получает префикс
    `bus_` сама собой (правило 5.1).
    """

    name = "bus"
    verbose_name = "Шина событий"
    default_auto_field = "django.db.models.BigAutoField"
