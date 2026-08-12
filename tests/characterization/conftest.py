import pytest


@pytest.fixture
def media_isolation(settings, tmp_path):
    """Чеки пишутся во временный каталог, а не в MEDIA_ROOT проекта."""
    settings.MEDIA_ROOT = tmp_path
