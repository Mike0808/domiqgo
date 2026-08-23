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

#: Причастия прошедшего времени не на `-ed`. Список закрытый и пополняется
#: только вместе с обоснованием: правило 4.1 требует прошедшего времени, а
#: `-ed` было лишь удобным приближением к нему — пока не встретилось первое
#: неправильное причастие.
#:
#: `Withdrawn` — отозванная версия тарифа (шаг C1). `Overdue` — просрочка
#: платежа: это вообще не причастие, а прилагательное, и событие названо так в
#: каталоге карты §5. Оно единственное временно́е: его никто не «совершает»,
#: оно наступает от того, что прошло время, — и «правильного» глагольного
#: имени у него нет.
IRREGULAR_PAST_FORMS = ("Withdrawn", "Overdue", "Sent", "Written", "Undone")


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
        if cls.name.endswith(IMPERATIVE_SUFFIXES)
        or not cls.name.endswith(("ed", *IRREGULAR_PAST_FORMS))
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: события именуются в прошедшем времени "
        f"(InvoiceIssued, PaymentConfirmed), а найдено: {', '.join(offenders)}. "
        "Если имя всё же в прошедшем времени, но не на «-ed» — впишите форму в "
        "IRREGULAR_PAST_FORMS с обоснованием, а не переименовывайте понятие "
        "под проверку."
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


#: Слой, из которого разрешено публиковать события (правило 4.4).
PUBLISHING_LAYER = "application"


def _layer_of(path: Path) -> str:
    parts = path.relative_to(MODULES_ROOT).parts
    return parts[1] if len(parts) > 1 else ""


@pytest.mark.parametrize(
    "path",
    [p for p in MODULES_ROOT.rglob("*.py") if _layer_of(p) != PUBLISHING_LAYER],
    ids=lambda p: str(p.name),
)
def test_bus_is_imported_only_from_application(path):
    """Правило 4.4: домен не знает, что у него есть подписчики.

    Проверка стала возможной на шаге B1: до него у шины не было имени, и
    место публикации отличить было нечем ([ADR-0027](../../docs/architecture/adr/0027-event-bus-lives-outside-modules.md)).
    Смотрим на импорт, а не только на вызов: модуль, притащивший `bus` в
    `domain/`, уже нарушил правило, даже если публикует пока где-то ещё.
    """
    offenders = [
        name
        for name in (
            *(alias.name
              for node in ast.walk(_parse(path)) if isinstance(node, ast.Import)
              for alias in node.names),
            *(node.module
              for node in ast.walk(_parse(path)) if isinstance(node, ast.ImportFrom)
              and node.module),
        )
        if name == "bus" or name.startswith("bus.")
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: шина импортируется только из "
        f"{PUBLISHING_LAYER}/, а здесь: {', '.join(offenders)}. Домен не знает, "
        "что у него есть подписчики; инфраструктура не знает, что произошло по "
        "существу."
    )


@pytest.mark.parametrize(
    "path",
    [p for p in MODULES_ROOT.rglob("*.py") if _layer_of(p) != PUBLISHING_LAYER],
    ids=lambda p: str(p.name),
)
def test_publish_is_called_only_from_application(path):
    """То же правило со стороны вызова — на случай реэкспорта имени.

    Импорт можно спрятать (`from ..application.bus_facade import publish`), а
    вызов — нет: имя `publish` в чужом слое подозрительно само по себе.
    """
    offenders = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "publish":
            offenders.append(f"строка {node.lineno}")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: publish() вызывается только из "
        f"{PUBLISHING_LAYER}/, а здесь — {', '.join(offenders)}."
    )


def test_bus_does_not_know_any_domain():
    """`bus/` — транспорт: ни одного события по имени он не знает.

    Дублирует контракт `bus-knows-no-domain` из `.importlinter` намеренно:
    инструмент недоступен локально (до PyPI из сети разработки нет доступа), а
    зависимость, направленная в обратную сторону, — это цикл, который дороже
    всего исправлять поздно.
    """
    offenders = []
    for path in (REPO_ROOT / "bus").rglob("*.py"):
        for name in (
            *(alias.name
              for node in ast.walk(_parse(path)) if isinstance(node, ast.Import)
              for alias in node.names),
            *(node.module
              for node in ast.walk(_parse(path)) if isinstance(node, ast.ImportFrom)
              and node.module),
        ):
            if name.split(".")[0] in ("modules", "billing"):
                offenders.append(f"{path.name}: {name}")
    assert not offenders, (
        "bus/ не импортирует предметные пакеты, а найдено: "
        + "; ".join(offenders)
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
