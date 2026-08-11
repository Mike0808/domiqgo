"""Чистота доменного слоя — шаг A2 плана миграции.

Дублирует контракт `domain-purity` из `.importlinter` намеренно: линтер
ставится отдельной зависимостью и запускается в CI, а этот тест работает в
базовом окружении. Правило слишком существенное, чтобы зависеть от того,
установлен ли инструмент.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "modules"

#: Домену запрещено знать о фреймворках и внешнем мире: только stdlib и
#: собственные доменные типы.
FORBIDDEN_IN_DOMAIN = ["django", "allauth", "requests", "celery", "rest_framework"]

#: ORM не появляется нигде, кроме infrastructure/.
FORBIDDEN_OUTSIDE_INFRASTRUCTURE = ["django.db"]


def _domain_files():
    return sorted(MODULES_ROOT.glob("*/domain/**/*.py"))


def _non_infrastructure_files():
    return sorted(
        p for p in MODULES_ROOT.rglob("*.py")
        if "infrastructure" not in p.relative_to(MODULES_ROOT).parts
    )


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module


def _matches(name: str, forbidden: str) -> bool:
    return name == forbidden or name.startswith(forbidden + ".")


@pytest.mark.parametrize("path", _domain_files(), ids=lambda p: str(p.name))
def test_domain_imports_nothing_but_stdlib(path):
    offenders = [
        name for name in _imports(path)
        if any(_matches(name, f) for f in FORBIDDEN_IN_DOMAIN)
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: домен не импортирует фреймворки — "
        + ", ".join(offenders)
    )


@pytest.mark.parametrize("path", _non_infrastructure_files(), ids=lambda p: str(p.name))
def test_orm_only_in_infrastructure(path):
    offenders = [
        name for name in _imports(path)
        if any(_matches(name, f) for f in FORBIDDEN_OUTSIDE_INFRASTRUCTURE)
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: ORM живёт только в infrastructure/ — "
        + ", ".join(offenders)
    )
