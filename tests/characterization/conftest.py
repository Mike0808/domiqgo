import pytest


@pytest.fixture
def media_isolation(settings, tmp_path):
    """Чеки пишутся во временный каталог, а не в MEDIA_ROOT проекта."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture(autouse=True)
def _settlement_wired():
    """Подписка сверки жива в каждом тесте (шаг E3) — см. billing.tests.settle."""
    from billing.tests.settle import wire

    wire()
