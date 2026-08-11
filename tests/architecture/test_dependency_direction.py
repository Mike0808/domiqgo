"""Направление зависимостей между модулями — правила §2 файла 05-rules.md.

Разрешённые обращения заданы матрицей: если пары нет в таблице, обращение
запрещено. Так новая зависимость требует осознанной правки этого файла, а не
проходит незамеченной.

Разбор через `ast`, без импорта пакетов: тест обязан работать до того, как
модули научатся импортироваться.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "modules"

#: Кто к кому вправе обращаться синхронно (через api/ чужого модуля).
#: Источник — §2 docs/architecture/05-rules.md и раздел «Зависимости»
#: каждой спецификации модуля.
ALLOWED: dict[str, set[str]] = {
    # Четыре листа графа: не обращаются ни к кому (правило 2.1).
    "identity": set(),
    "properties": set(),
    "metering": set(),
    "tariffs": set(),
    # Tenancy: договор заключается с учётной записью и на объект.
    "tenancy": {"identity", "properties"},
    # Billing: собирает счёт из четырёх источников. Payments — нет (2.2).
    "billing": {"tenancy", "properties", "metering", "tariffs"},
    # Payments: единственный вопрос — какие счета не погашены (ADR-0014).
    "payments": {"billing"},
    # Notifications: ровно то, чего не хватает в событиях для текста (2.7).
    "notifications": {"tenancy", "properties"},
    # Reporting: читает всех, от него не зависит никто (2.6).
    "reporting": {
        "identity", "properties", "tenancy", "metering",
        "tariffs", "billing", "payments", "notifications",
    },
}

#: Модули, которых не вправе вызывать доменные модули (2.5, 2.6).
NEVER_CALLED = {"notifications", "reporting"}


def _python_files():
    return sorted(MODULES_ROOT.rglob("*.py"))


def _imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                pkg = path.parent.relative_to(REPO_ROOT).parts
                base = pkg[: len(pkg) - node.level + 1]
                yield ".".join([*base, *([node.module] if node.module else [])])
            elif node.module:
                yield node.module


def _owner(path: Path) -> str:
    return path.relative_to(MODULES_ROOT).parts[0]


def test_allowed_matrix_covers_every_module():
    """Матрица не разошлась с составом modules/."""
    present = {
        p.name for p in MODULES_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    }
    assert present == set(ALLOWED), (
        "матрица §2 разошлась с modules/: "
        f"нет в матрице {sorted(present - set(ALLOWED))}, "
        f"нет на диске {sorted(set(ALLOWED) - present)}"
    )


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.name))
def test_module_calls_only_allowed_modules(path):
    """Обращение к чужому api/ разрешено только по матрице."""
    owner = _owner(path)
    violations = []
    for name in _imported_names(path):
        parts = name.split(".")
        if len(parts) < 2 or parts[0] != "modules":
            continue
        target = parts[1]
        if target == owner or target not in ALLOWED:
            continue
        if target not in ALLOWED[owner]:
            violations.append(name)
    assert not violations, (
        f"{path.relative_to(REPO_ROOT)}: модуль «{owner}» не вправе обращаться к "
        + ", ".join(sorted({v.split('.')[1] for v in violations}))
        + f" ({', '.join(violations)}). Разрешено: "
        + (", ".join(sorted(ALLOWED[owner])) or "никто")
        + ". Нужна новая зависимость — правьте матрицу и §2 правил осознанно."
    )


def test_leaves_depend_on_nobody():
    """Правило 2.1: четыре листа графа не обращаются ни к кому."""
    leaves = {"identity", "properties", "metering", "tariffs"}
    wrong = {m: sorted(ALLOWED[m]) for m in leaves if ALLOWED[m]}
    assert not wrong, f"листы графа обзавелись зависимостями: {wrong}"


def test_notifications_and_reporting_are_never_called_by_domain_modules():
    """Правила 2.5 и 2.6: доменные модули их не вызывают.

    Reporting здесь не в счёт: он читает всех, в том числе журнал доставки
    Notifications, и сам остаётся листом с другой стороны.
    """
    callers = {
        m: sorted(deps & NEVER_CALLED)
        for m, deps in ALLOWED.items()
        if m != "reporting" and deps & NEVER_CALLED
    }
    assert not callers, (
        "доменные модули не вызывают Notifications и Reporting, а в матрице "
        f"значатся вызовы: {callers}"
    )


def test_synchronous_graph_has_no_mutual_pairs():
    """В синхронном графе нет ни одной взаимной пары — включая Billing и Payments.

    Пару Billing ↔ Payments называют взаимной, и по смыслу она такова: Payments
    спрашивает Billing про непогашенные счета, Billing узнаёт о платежах от
    Payments. Но второе направление — события, а не вызовы, и потому в этой
    матрице его нет. Ровно это и удерживает систему от цикла (ADR-0014,
    ADR-0015): стоит кому-нибудь добавить сюда billing → payments «чтобы
    честно спросить источник истины», как тест покраснеет.
    """
    mutual = sorted(
        {
            tuple(sorted((a, b)))
            for a, deps in ALLOWED.items()
            for b in deps
            if a in ALLOWED.get(b, set())
        }
    )
    assert not mutual, (
        f"взаимные синхронные вызовы: {mutual}. Обратное направление должно "
        "идти событием, а не вызовом."
    )
