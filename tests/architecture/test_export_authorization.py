"""ADR-0023: ни один вход не вызывает `RunExport` в обход слоя авторизации.

Правило фазы 4: право запрашивающего проверяет прикладной слой, а Reporting
лишь пишет инициатора в журнал. Проверка статическая: `run_export` зовут
только сам модуль и два входа — админка (персонал) и кабинет жильца
(собственная учётная запись); каждый вход передаёт `request.user.pk`.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Входы, которым разрешено запускать выгрузку. Новый вход добавляется сюда
#: осознанно — вместе со своей проверкой права.
ALLOWED_CALLERS = {
    REPO_ROOT / "billing" / "views.py",
    REPO_ROOT / "modules" / "reporting" / "infrastructure" / "admin.py",
    REPO_ROOT / "modules" / "reporting" / "api" / "__init__.py",
    REPO_ROOT / "modules" / "reporting" / "application" / "commands.py",
}


def _calls_run_export(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "run_export":
                yield node


def test_run_export_is_called_only_behind_authorization():
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts:
            continue
        if any(True for _ in _calls_run_export(path)) and path not in ALLOWED_CALLERS:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "RunExport зовут в обход слоя авторизации (ADR-0023): "
        + ", ".join(offenders))


def test_every_entry_point_passes_the_authenticated_initiator():
    """Инициатор — из сессии, не из параметров запроса."""
    for path in (REPO_ROOT / "billing" / "views.py",
                 REPO_ROOT / "modules" / "reporting" / "infrastructure" / "admin.py"):
        source = path.read_text(encoding="utf-8")
        calls = list(_calls_run_export(path))
        assert calls, f"{path}: вход перестал звать run_export — обновите тест"
        for node in calls:
            segment = ast.get_source_segment(source, node)
            assert "request.user.pk" in segment, (
                f"{path}: run_export без request.user.pk — инициатора "
                "обязана давать сессия")
