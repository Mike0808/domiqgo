"""Поведение шины: доставка после коммита и изоляция ошибки подписчика.

Требования шага B1 плана миграции: реестр подписчиков, публикация, доставка
после коммита транзакции, изоляция ошибки подписчика от транзакции издателя.
Ни один существующий сценарий на этом шаге событий не публикует — шина
проверяется учебным событием.
"""

from dataclasses import dataclass
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from bus import clear_subscribers, publish, subscribe

#: `transaction=True`, а не обычный `django_db`, и это не про скорость.
#: Обычный `django_db` заворачивает тест в транзакцию, которая **никогда не
#: фиксируется**, — а шина доставляет после фиксации. Под ним не приходит ни
#: одно событие (см. `test_events_never_arrive_under_the_default_db_mark`).
#: Здесь нужна настоящая фиксация, иначе проверять нечего.
pytestmark = pytest.mark.django_db(transaction=True)


@dataclass(frozen=True)
class LessonLearned:
    """Учебное событие. Форма — как у настоящих: прошедшее время в имени,
    в payload только идентификаторы и примитивы (правила 4.1 и 4.2)."""
    lesson_id: int
    subject: str
    weight: Decimal


@dataclass(frozen=True)
class OtherThingHappened:
    thing_id: int


@pytest.fixture(autouse=True)
def _empty_registry():
    """Реестр — модульное состояние; без очистки подписка одного теста
    доживает до следующего."""
    clear_subscribers()
    yield
    clear_subscribers()


def _collector(into):
    def handler(event):
        into.append(event)
    return handler


def _explode(event):
    raise RuntimeError("подписчик сломан")


# --------------------------------------------------------------------------
# Публикация и подписка
# --------------------------------------------------------------------------

def test_subscriber_receives_the_event_it_asked_for():
    received = []
    subscribe(LessonLearned, _collector(received))

    event = LessonLearned(lesson_id=1, subject="шина", weight=Decimal("0.5"))
    publish(event)

    assert received == [event]


def test_subscriber_does_not_receive_other_types():
    received = []
    subscribe(LessonLearned, _collector(received))

    publish(OtherThingHappened(thing_id=7))

    assert received == []


def test_event_without_subscribers_is_published_without_complaint():
    """Половина событий P1 подписчиков не имеет — это норма, а не ошибка
    (§8 правил: «каждое событие обязано иметь подписчика» правилом не является)."""
    publish(LessonLearned(lesson_id=2, subject="никому", weight=Decimal("0")))


def test_handlers_are_called_in_subscription_order():
    order = []
    subscribe(LessonLearned, lambda e: order.append("first"))
    subscribe(LessonLearned, lambda e: order.append("second"))

    publish(LessonLearned(lesson_id=3, subject="порядок", weight=Decimal("1")))

    assert order == ["first", "second"]


def test_subscribing_the_same_handler_twice_delivers_once():
    """`AppConfig.ready` вызывается дважды при автоперезагрузке runserver —
    событие от этого не должно приходить дважды."""
    received = []
    handler = _collector(received)
    subscribe(LessonLearned, handler)
    subscribe(LessonLearned, handler)

    publish(LessonLearned(lesson_id=4, subject="дважды", weight=Decimal("2")))

    assert len(received) == 1


# --------------------------------------------------------------------------
# Доставка после коммита
# --------------------------------------------------------------------------

def test_delivery_waits_for_the_commit():
    """Подписчик не видит факт, который ещё может откатиться."""
    received = []
    subscribe(LessonLearned, _collector(received))
    event = LessonLearned(lesson_id=5, subject="после коммита",
                          weight=Decimal("3"))

    with transaction.atomic():
        publish(event)
        assert received == []          # транзакция ещё не зафиксирована

    assert received == [event]         # доставлено на выходе из блока


@pytest.mark.django_db
def test_events_never_arrive_under_the_default_db_mark(
        django_capture_on_commit_callbacks):
    """Ловушка, которую стоит знать до того, как в неё попадёшь.

    Обычный `django_db` держит тест в транзакции, которая не фиксируется
    никогда, поэтому шина не доставляет ничего — и выглядит сломанной. Тест
    модуля, ожидающий события, обязан либо просить `transaction=True`, либо
    пользоваться `django_capture_on_commit_callbacks`. Проверка стоит здесь,
    чтобы это свойство было записано, а не выяснялось заново каждым, кто
    напишет первый тест с событием.
    """
    received = []
    subscribe(LessonLearned, _collector(received))
    event = LessonLearned(lesson_id=12, subject="ловушка", weight=Decimal("10"))

    publish(event)
    assert received == []                                   # тишина

    with django_capture_on_commit_callbacks(execute=True):   # так — приходит
        publish(event)
    assert received == [event]


def test_rolled_back_transaction_delivers_nothing():
    """Отменённый факт не порождает события — иначе подписчик узнаёт о том,
    чего не произошло."""
    received = []
    subscribe(LessonLearned, _collector(received))

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            User.objects.create_user("ephemeral", password="pass12345")
            publish(LessonLearned(lesson_id=6, subject="откат",
                                  weight=Decimal("4")))
            raise RuntimeError("издатель передумал")

    assert received == []
    assert not User.objects.filter(username="ephemeral").exists()


def test_publishing_outside_a_transaction_delivers_immediately():
    """Публиковать вне транзакции значит, что фиксировать нечего: Django
    выполняет обратный вызов сразу, и это верное поведение, а не обход."""
    received = []
    subscribe(LessonLearned, _collector(received))

    publish(LessonLearned(lesson_id=7, subject="без транзакции",
                          weight=Decimal("5")))

    assert len(received) == 1


# --------------------------------------------------------------------------
# Изоляция ошибки подписчика
# --------------------------------------------------------------------------

def test_failing_subscriber_does_not_roll_back_the_publisher():
    """Главное требование шага: чужая поломка не отменяет свершившийся факт."""
    subscribe(LessonLearned, _explode)

    with transaction.atomic():
        User.objects.create_user("survivor", password="pass12345")
        publish(LessonLearned(lesson_id=8, subject="изоляция",
                              weight=Decimal("6")))

    assert User.objects.filter(username="survivor").exists()


def test_failing_subscriber_does_not_reach_the_publishers_caller():
    """Падение подписчика не должно превращаться в ошибку запроса.

    Обратные вызовы `on_commit` выполняются при выходе из `atomic()`, поэтому
    без изоляции исключение ушло бы наружу — в обработчик HTTP, то есть в 500
    у жильца, чьё показание при этом сохранилось.
    """
    subscribe(LessonLearned, _explode)

    with transaction.atomic():            # выход из блока не поднимает ничего
        publish(LessonLearned(lesson_id=9, subject="тишина", weight=Decimal("7")))


def test_failing_subscriber_does_not_block_the_others():
    """Соседи получают событие, а сломанный подписчик не первый и не последний
    по счёту — проверяется, что цикл не рвётся ни в начале, ни в середине."""
    received = []
    subscribe(LessonLearned, _collector(received))
    subscribe(LessonLearned, _explode)
    subscribe(LessonLearned, _collector(received))

    publish(LessonLearned(lesson_id=10, subject="соседи", weight=Decimal("8")))

    assert len(received) == 2


def test_failure_is_logged_with_the_stack(caplog):
    """Ошибка не проглатывается: единственный след — лог `bus`."""
    subscribe(LessonLearned, _explode)

    with caplog.at_level("ERROR", logger="bus"):
        publish(LessonLearned(lesson_id=11, subject="след", weight=Decimal("9")))

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.exc_info is not None            # стек, а не только сообщение
    assert "LessonLearned" in record.getMessage()
    assert "_explode" in record.getMessage()
