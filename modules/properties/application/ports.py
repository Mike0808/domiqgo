"""Порт хранилища: то, что `application/` вправе требовать от инфраструктуры.

Правило 3.5 запрещает `application/` обращаться к `infrastructure/` напрямую;
реализацию подставляет `api/`.
"""

from typing import Protocol


class PropertyRepository(Protocol):
    def load(self, apartment_id: int): ...

    def load_all(self, include_decommissioned: bool) -> list: ...

    def save_service_state(self, apartment) -> None: ...

    def save_description(self, apartment) -> None: ...

    def create(self, label: str, address: str, has_cold_water: bool,
               has_hot_water: bool, has_sewage: bool,
               gvs_heat_norm) -> int: ...
