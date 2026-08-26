"""Чтение: один объект и перечень объектов."""

from .ports import PropertyRepository


def get_property(repository: PropertyRepository, apartment_id: int):
    return repository.load(apartment_id)


def list_properties(repository: PropertyRepository,
                    include_decommissioned: bool = False) -> list:
    """Перечень объектов. Выведенные из эксплуатации по умолчанию скрыты —
    иначе список владельца с годами зарастает проданными квартирами."""
    return repository.load_all(include_decommissioned)
