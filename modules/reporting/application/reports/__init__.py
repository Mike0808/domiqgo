"""Сборщики отчётов: публичные запросы чужих модулей → строки файла.

Reporting ничего не вычисляет — итоговые строки в XLSX несут формулы, и
складывает их Excel, а не модуль (спецификация: появление числа, которого
нет ни в одном модуле, — признак нужды в Analytics, а не повод считать).
"""

from datetime import datetime, timezone


#: Метаданные документов приходят извне: модуля Documents нет, его граница
#: лишь зафиксирована (ADR-0022), и провайдер `ListDocumentsMeta(tenancy_id)`
#: внедряет интерфейсный слой — как резолвер владельцев в Notifications (F3).
_documents_meta = None


def wire(documents_meta) -> None:
    global _documents_meta
    _documents_meta = documents_meta


def documents_meta(tenancy_id: int) -> list[dict]:
    return _documents_meta(tenancy_id) if _documents_meta else []


def build(entry, run, params):
    from . import financial, full, my_data, registry

    builders = {"financial": financial.build, "registry": registry.build,
                "full": full.build, "my_data": my_data.build}
    stamp = datetime.now(timezone.utc)
    return builders[entry.code](run, stamp, params)
