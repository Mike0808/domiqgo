"""Границы модулей — шаг A2 плана миграции.

Проверяется разбором исходников (`ast`), без импорта пакетов и без внешних
зависимостей: тесты обязаны работать в том же окружении, что и остальной
прогон, а `.importlinter` ставится отдельно и запускается в CI.

Разделение с `.importlinter`: там слои внутри модуля и чистота `domain` от
фреймворков; здесь — правила, требующие перебора всех пар модулей.

Приложение `billing/` не проверяется: оно объявлено устаревающим слоем и
подпадёт под контракты только после расформирования (§2 плана миграции).
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "modules"

MODULES = [
    "identity", "properties", "tenancy", "metering", "tariffs",
    "billing", "payments", "notifications", "reporting",
]
LAYERS = ["api", "events", "domain", "application", "infrastructure"]

#: Слои, которые чужой модуль импортировать не вправе. Публичны только
#: api/ и events/.
INTERNAL_LAYERS = ["domain", "application", "infrastructure"]


def _python_files():
    return sorted(MODULES_ROOT.rglob("*.py"))


def _imported_names(path: Path):
    """Полные имена всех импортов файла, включая относительные."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Относительный импорт: разворачиваем в абсолютный, чтобы
                # `from ...domain import X` тоже попал под проверку.
                pkg = path.parent.relative_to(REPO_ROOT).parts
                base = pkg[: len(pkg) - node.level + 1]
                yield ".".join([*base, *( [node.module] if node.module else [] )])
            elif node.module:
                yield node.module


def _owning_module(path: Path) -> str:
    return path.relative_to(MODULES_ROOT).parts[0]


def test_skeleton_is_complete():
    """У каждого модуля заведены все пять слоёв."""
    missing = [
        f"modules/{m}/{layer}"
        for m in MODULES
        for layer in LAYERS
        if not (MODULES_ROOT / m / layer / "__init__.py").is_file()
    ]
    assert not missing, "нет пакетов: " + ", ".join(missing)


def test_no_unexpected_top_level_packages():
    """В modules/ не заводятся каталоги мимо утверждённой карты."""
    found = {
        p.name for p in MODULES_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    }
    assert found == set(MODULES), (
        "modules/ разошёлся с картой: лишние "
        f"{sorted(found - set(MODULES))}, отсутствуют {sorted(set(MODULES) - found)}"
    )


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.name))
def test_module_does_not_import_foreign_internals(path):
    """Извне модуля видны только api/ и events/.

    Внутренности чужого модуля — domain/, application/, infrastructure/ —
    не импортируются ни при каких условиях: связь идёт через публичный API,
    событие или Query Service.
    """
    owner = _owning_module(path)
    violations = []
    for name in _imported_names(path):
        parts = name.split(".")
        if len(parts) < 3 or parts[0] != "modules":
            continue
        target, layer = parts[1], parts[2]
        if target != owner and layer in INTERNAL_LAYERS:
            violations.append(name)
    assert not violations, (
        f"{path.relative_to(REPO_ROOT)} импортирует внутренности чужого модуля: "
        + ", ".join(violations)
        + ". Допустимы только modules.<чужой>.api и modules.<чужой>.events."
    )


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.name))
def test_modules_do_not_import_legacy_billing_app(path):
    """Новый код не тянет устаревающее приложение billing/."""
    offenders = [
        name for name in _imported_names(path)
        if name == "billing" or name.startswith("billing.")
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} импортирует устаревающее приложение: "
        + ", ".join(offenders)
    )
