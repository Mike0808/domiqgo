"""Сборщики отчётов: публичные запросы чужих модулей → строки файла.

Reporting ничего не вычисляет — итоговые строки в XLSX несут формулы, и
складывает их Excel, а не модуль (спецификация: появление числа, которого
нет ни в одном модуле, — признак нужды в Analytics, а не повод считать).
"""

from datetime import datetime, timezone


def build(entry, run, params):
    from . import financial, registry

    builders = {"financial": financial.build, "registry": registry.build}
    stamp = datetime.now(timezone.utc)
    return builders[entry.code](run, stamp, params)
