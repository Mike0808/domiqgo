"""Подписка модуля на события Properties.

Единственное место модуля, где имя `bus` встречается ради подписки, а не
публикации: правило 4.4 держит шину в `application/`, и `apps.py` вызывает
эту функцию, не зная о шине сам.
"""

from bus import subscribe
from modules.properties.events import PropertyDecommissioned, PropertyRecommissioned

from . import handlers


def wire(repository) -> None:
    """Повторный вызов безвреден: шина игнорирует повторную подписку того же
    обработчика, а обработчики здесь — модульные функции, не замыкания."""
    subscribe(PropertyDecommissioned, _on_decommissioned)
    subscribe(PropertyRecommissioned, _on_recommissioned)
    global _repository
    _repository = repository


_repository = None


def _on_decommissioned(event: PropertyDecommissioned) -> None:
    handlers.property_decommissioned(_repository, event)


def _on_recommissioned(event: PropertyRecommissioned) -> None:
    handlers.property_recommissioned(_repository, event)
