import pytest

from billing.tests.settle import wire


@pytest.fixture(autouse=True)
def _settlement_wired():
    """Подписка сверки жива в каждом тесте — см. settle.wire."""
    wire()
