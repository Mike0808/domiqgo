"""Контракты событий и правила хранения — §4 и §5 файла 05-rules.md.

Проверки статические (`ast`), поэтому работают до того, как модули научатся
импортироваться, и не требуют поднятия Django.

Пока `modules/` пуст, часть проверок ничего не находит и проходит вхолостую.
Это сделано намеренно: контракт включается раньше кода, чтобы нарушить его
незаметно было уже нельзя.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "modules"

#: Допустимые типы полей payload события: идентификаторы и примитивы.
#: Объект модели в payload привязывает подписчика к чужой схеме (правило 4.2).
PRIMITIVE_ANNOTATIONS = {
    "int", "str", "bool", "float", "bytes",
    "Decimal", "date", "datetime", "time", "UUID",
    "None", "Any",
}

#: Окончания, выдающие повелительное наклонение вместо прошедшего (4.1).
IMPERATIVE_SUFFIXES = ("Command", "Request", "Do", "Create", "Update", "Delete")


def _files(pattern: str):
    return sorted(MODULES_ROOT.glob(pattern))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _classes(tree: ast.Module):
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def _annotation_names(node: ast.AST):
    """Все идентификаторы, встречающиеся в аннотации типа."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            yield sub.id
        elif isinstance(sub, ast.Attribute):
            yield sub.attr
        elif isinstance(sub, ast.Constant) and sub.value is None:
            yield "None"


# --------------------------------------------------------------------------
# §4. События
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", _files("*/events/**/*.py"), ids=lambda p: str(p.name))
def test_event_names_are_past_tense(path):
    """Правило 4.1: имя события — свершившийся факт, а не поручение."""
    offenders = [
        cls.name
        for cls in _classes(_parse(path))
        if cls.name.endswith(IMPERATIVE_SUFFIXES) or not cls.name.endswith("ed")
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: события именуются в прошедшем времени "
        f"(InvoiceIssued, PaymentConfirmed), а найдено: {', '.join(offenders)}"
    )


@pytest.mark.parametrize("path", _files("*/events/**/*.py"), ids=lambda p: str(p.name))
def test_event_payload_is_primitives_only(path):
    """Правило 4.2: в payload только идентификаторы и примитивы."""
    offenders = []
    for cls in _classes(_parse(path)):
        for stmt in cls.body:
            if not isinstance(stmt, ast.AnnAssign) or stmt.annotation is None:
                continue
            names = set(_annotation_names(stmt.annotation))
            exotic = names - PRIMITIVE_ANNOTATIONS - {
                "list", "tuple", "frozenset", "Sequence", "Optional", "Union"
            }
            if exotic:
                field = getattr(stmt.target, "id", "?")
                offenders.append(f"{cls.name}.{field}: {', '.join(sorted(exotic))}")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: payload события несёт не примитивы — "
        + "; ".join(offenders)
        + ". Объект модели в payload ломается при первом изменении чужой схемы."
    )


@pytest.mark.parametrize(
    "path",
    [p for p in MODULES_ROOT.rglob("*.py")],
    ids=lambda p: str(p.name),
)
def test_no_django_signals_between_modules(path):
    """Правило 4.3: сигнал — невидимая связь, её нет ни в импортах, ни в графе."""
    offenders = [
        name
        for name in (
            alias.name
            for node in ast.walk(_parse(path))
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if name.startswith("django.dispatch")
    ] + [
        node.module
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.ImportFrom)
        and node.module
        and (
            node.module.startswith("django.dispatch")
            or node.module.startswith("django.db.models.signals")
        )
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: django signals между модулями запрещены "
        f"({', '.join(offenders)}) — реакция на чужой факт идёт доменным событием."
    )


# --------------------------------------------------------------------------
# §5. Владение данными
# --------------------------------------------------------------------------

def _model_classes(tree: ast.Module):
    """Классы, наследующие models.Model."""
    for cls in _classes(tree):
        for base in cls.bases:
            name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
            if name == "Model":
                yield cls


@pytest.mark.parametrize(
    "path",
    [p for p in MODULES_ROOT.rglob("*.py")
     if "infrastructure" not in p.relative_to(MODULES_ROOT).parts],
    ids=lambda p: str(p.name),
)
def test_models_declared_only_in_infrastructure(path):
    """Правило 3.3: модель — деталь хранения, ей место в infrastructure/."""
    offenders = [cls.name for cls in _model_classes(_parse(path))]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: Django-модели объявляются только в "
        f"infrastructure/, а здесь: {', '.join(offenders)}"
    )


@pytest.mark.parametrize("path", _files("*/infrastructure/**/*.py"), ids=lambda p: str(p.name))
def test_no_foreign_keys_at_all_in_new_code(path):
    """Правила 1.3 и 5.2: ссылка на чужую сущность — идентификатор без констрейнта.

    Проверка намеренно строже правила: в новом коде запрещён любой
    `ForeignKey`, а не только межмодульный. Отличить свой от чужого статически
    можно лишь по строке-цели, которую легко записать так, что анализ её не
    разберёт. Внутримодульная связь, если она действительно понадобится,
    добавляется правкой этого списка с обоснованием — как и любое исключение.
    """
    source = path.read_text(encoding="utf-8")
    offenders = [
        kind for kind in ("ForeignKey", "OneToOneField", "ManyToManyField")
        if kind in source
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: {', '.join(offenders)} в новом коде — "
        "ссылка на чужую сущность идёт идентификатором без констрейнта, иначе "
        "таблицы двух модулей нельзя разделить без остановки."
    )


@pytest.mark.parametrize("path", _files("*/infrastructure/**/*.py"), ids=lambda p: str(p.name))
def test_table_names_are_prefixed_with_module(path):
    """Правило 5.1: имя таблицы начинается с имени модуля-владельца."""
    module = path.relative_to(MODULES_ROOT).parts[0]
    tree = _parse(path)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [getattr(t, "id", "") for t in node.targets]
        if "db_table" not in targets:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            table = node.value.value
            if not table.startswith(f"{module}_"):
                offenders.append(table)
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: таблицы модуля «{module}» именуются с "
        f"префиксом «{module}_», а найдено: {', '.join(offenders)}"
    )
