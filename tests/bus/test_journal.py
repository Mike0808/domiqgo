"""Журнал опубликованных событий — шаг B2 плана миграции.

Журнал существует ради одного требования: ADR-0015 разрешает Billing держать
проекцию признанных оплат при условии, что она перестраиваема. Отсюда всё, что
здесь проверяется: запись возникает от самого факта публикации (а не от
доставки), переживает отсутствие подписчиков, не переживает откат и ложится в
порядке, пригодном для пересборки.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from bus import clear_subscribers, publish, subscribe
from bus.models import PublishedEvent

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass(frozen=True)
class InvoiceIssuedLikeEvent:
    """Форма настоящего события: прошедшее время, только примитивы."""
    invoice_id: int
    period: date
    total: Decimal
    dry_run: bool


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_subscribers()
    yield
    clear_subscribers()


def _event(invoice_id=1):
    return InvoiceIssuedLikeEvent(
        invoice_id=invoice_id, period=date(2026, 7, 1),
        total=Decimal("22950.00"), dry_run=False)


# --------------------------------------------------------------------------
# Что попадает в журнал
# --------------------------------------------------------------------------

def test_publication_is_recorded():
    publish(_event())

    entry = PublishedEvent.objects.get()
    assert entry.event_type.endswith(".InvoiceIssuedLikeEvent")
    assert entry.published_at is not None


def test_payload_keeps_every_field():
    publish(_event(invoice_id=42))

    payload = PublishedEvent.objects.get().payload
    assert set(payload) == {"invoice_id", "period", "total", "dry_run"}
    assert payload["invoice_id"] == 42
    assert payload["dry_run"] is False


def test_decimal_and_date_survive_as_parseable_strings():
    """`DjangoJSONEncoder` укладывает их в строки — при пересборке разбираются
    обратно однозначно. Точность денег при этом не теряется, в отличие от
    `float`."""
    publish(_event())

    payload = PublishedEvent.objects.get().payload
    assert payload["total"] == "22950.00"
    assert payload["period"] == "2026-07-01"
    assert Decimal(payload["total"]) == Decimal("22950.00")
    assert date.fromisoformat(payload["period"]) == date(2026, 7, 1)


def test_event_type_is_the_full_class_path():
    """Строка, а не импорт: шина по-прежнему не знает ни одного события."""
    publish(_event())

    assert PublishedEvent.objects.get().event_type == (
        f"{InvoiceIssuedLikeEvent.__module__}.InvoiceIssuedLikeEvent")


def test_event_that_is_not_a_dataclass_is_refused():
    """Единственное требование шины к форме события."""
    class NotADataclass:
        pass

    with pytest.raises(TypeError, match="датакласс"):
        publish(NotADataclass())

    assert not PublishedEvent.objects.exists()


# --------------------------------------------------------------------------
# Журнал пишет публикацию, а не доставку
# --------------------------------------------------------------------------

def test_event_without_subscribers_is_still_recorded():
    """Половина событий P1 подписчиков не имеет; для пересборки они нужны
    ровно так же, как остальные."""
    publish(_event())

    assert PublishedEvent.objects.count() == 1


def test_failing_subscriber_does_not_erase_the_record():
    """Журнал фиксирует, что событие было, а не что его кто-то принял."""
    subscribe(InvoiceIssuedLikeEvent,
              lambda e: (_ for _ in ()).throw(RuntimeError("подписчик сломан")))

    publish(_event())

    assert PublishedEvent.objects.count() == 1


def test_record_appears_before_the_commit():
    """Запись идёт в транзакции издателя, а не после неё, — иначе журнал и
    факт могли бы разойтись."""
    with transaction.atomic():
        publish(_event())
        assert PublishedEvent.objects.count() == 1   # ещё до фиксации

    assert PublishedEvent.objects.count() == 1


@pytest.mark.django_db          # не transaction=True: фиксации не будет вовсе
def test_record_is_written_even_when_delivery_never_runs():
    """Та же граница, но с другой стороны и другим механизмом.

    Обычный `django_db` держит тест в транзакции, которая не фиксируется
    никогда, поэтому доставка не выполняется ни разу
    (`test_events_never_arrive_under_the_default_db_mark`). Журнальная запись
    при этом обязана быть: её пишет публикация, а не доставка.
    """
    publish(_event())

    assert PublishedEvent.objects.count() == 1


# --------------------------------------------------------------------------
# Отличие от outbox
# --------------------------------------------------------------------------

def test_rollback_takes_the_record_with_it():
    """Здесь журнал ведёт себя противоположно outbox.

    Outbox обязан пережить откат доставки; журнал обязан **не** пережить откат
    транзакции — иначе при пересборке всплывёт счёт, которого никогда не было.
    """
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            User.objects.create_user("ephemeral", password="pass12345")
            publish(_event())
            raise RuntimeError("издатель передумал")

    assert not PublishedEvent.objects.exists()
    assert not User.objects.filter(username="ephemeral").exists()


def test_journal_has_no_delivery_state():
    """Поля «доставлено» нет и не будет: журнал не претендует на гарантию
    доставки (§2.6 оценки, задел на outbox — P2)."""
    fields = {f.name for f in PublishedEvent._meta.get_fields()}
    assert fields == {"id", "event_type", "payload", "published_at"}


# --------------------------------------------------------------------------
# Пригодность к пересборке
# --------------------------------------------------------------------------

def test_records_are_ordered_by_insertion_not_by_time():
    """Два события одной транзакции получают неразличимую метку времени —
    порядок пересборки даёт первичный ключ."""
    with transaction.atomic():
        publish(_event(invoice_id=1))
        publish(_event(invoice_id=2))
        publish(_event(invoice_id=3))

    ids = [e.payload["invoice_id"] for e in PublishedEvent.objects.all()]
    assert ids == [1, 2, 3]
