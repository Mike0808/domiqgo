"""Админка Tariffs — единственный способ завести ставку, и потому единственный
путь, по которому события вообще наступают.

Тесты идут через настоящий HTTP-запрос к админке, а не через `save_model`:
проверяется не метод, а связка «форма → команда → домен → репозиторий → шина».
Вызов API напрямую этой связки не касается и молчаливого возврата к обычному
CRUD не заметит.

`transaction=True` во всём файле — иначе шина не доставит ничего
(`tests/bus/test_bus.py::test_events_never_arrive_under_the_default_db_mark`).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from bus.models import PublishedEvent
from modules.tariffs import api
from modules.tariffs.infrastructure.models import TariffVersion

pytestmark = pytest.mark.django_db(transaction=True)

JULY = date(2026, 7, 1)
CHANGELIST = "/admin/tariffs/tariffversion/"


@pytest.fixture
def owner():
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    client = Client()
    client.login(username="boss", password="pass12345")
    return client


def _form(**overrides):
    fields = {
        "utility": "cold_water",
        "rate": "48.15",
        "effective_from": "2026-07-01",
        "source_name": "",
        "source_url": "",
    }
    fields.update(overrides)
    return fields


def _published():
    return [e.event_type.rsplit(".", 1)[-1] for e in PublishedEvent.objects.all()]


# ------------------------------------------------------------------- команды

def test_adding_a_version_goes_through_the_publish_command(owner):
    response = owner.post(f"{CHANGELIST}add/", _form())

    assert response.status_code == 302        # не 200 с формой и ошибками
    assert _published() == ["TariffVersionPublished"]
    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")


def test_save_and_continue_editing_lands_on_the_written_row(owner):
    """Репозиторий переписывает линию целиком, и объект формы остаётся без
    ключа: команда вернула не ту строку, что создала форма. Админка ключ
    перечитывает — иначе «Сохранить и продолжить редактирование» уводит в
    никуда на совершенно исправной операции.

    Проверяется именно эта кнопка: обычное «Сохранить» ведёт на список, где
    ключ не нужен, и поломку не показывает.
    """
    response = owner.post(f"{CHANGELIST}add/", {**_form(), "_continue": "1"})

    written = TariffVersion.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"{CHANGELIST}{written.pk}/change/"


def test_editing_a_version_corrects_it_instead_of_adding_a_second(owner):
    api.publish_tariff_version("cold_water", Decimal("4.85"), JULY)
    pk = TariffVersion.objects.get().pk

    owner.post(f"{CHANGELIST}{pk}/change/", _form(rate="48.15"))

    assert TariffVersion.objects.count() == 1
    assert api.get_rate_on("cold_water", JULY).rate == Decimal("48.15")
    assert _published()[-1] == "TariffVersionCorrected"


def test_editing_can_move_the_date(owner):
    api.publish_tariff_version("cold_water", Decimal("48.15"), date(2026, 7, 11))
    pk = TariffVersion.objects.get().pk

    owner.post(f"{CHANGELIST}{pk}/change/", _form(effective_from="2026-07-01"))

    assert [v.effective_from for v in api.list_versions("cold_water")] == [JULY]


def test_utility_cannot_be_changed_on_an_existing_version(owner):
    """Смена услуги — не правка, а перенос между линиями: отзыв в одной и
    публикация в другой. Команды такой операции нет, и подмена поля в форме
    не должна её изобретать."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    pk = TariffVersion.objects.get().pk

    owner.post(f"{CHANGELIST}{pk}/change/", _form(utility="sewage"))

    assert api.get_rate_on("cold_water", JULY) is not None
    assert api.get_rate_on("sewage", JULY) is None


def test_deleting_a_version_goes_through_the_withdraw_command(owner):
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    pk = TariffVersion.objects.get().pk

    owner.post(f"{CHANGELIST}{pk}/delete/", {"post": "yes"})

    assert api.get_rate_on("cold_water", JULY) is None
    assert _published()[-1] == "TariffVersionWithdrawn"


def test_bulk_delete_withdraws_every_selected_version(owner):
    api.publish_tariff_version("cold_water", Decimal("40.00"), date(2026, 1, 1))
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    pks = [str(v.pk) for v in TariffVersion.objects.all()]

    owner.post(CHANGELIST, {"action": "delete_selected",
                            "_selected_action": pks, "post": "yes"})

    assert api.list_versions("cold_water") == []
    assert _published().count("TariffVersionWithdrawn") == 2


# -------------------------------------------------------------- объяснение

def test_the_add_form_says_a_new_version_is_a_price_change(owner):
    page = owner.get(f"{CHANGELIST}add/").content.decode()

    assert "Новая версия — это изменение цены" in page


def test_the_change_form_warns_that_no_new_version_will_appear(owner):
    """Различение публикации и исправления до сих пор было видно везде, кроме
    формы, на которой владелец принимает решение."""
    api.publish_tariff_version("cold_water", Decimal("48.15"), JULY)
    pk = TariffVersion.objects.get().pk

    page = owner.get(f"{CHANGELIST}{pk}/change/").content.decode()

    assert "новой версии не появится" in page
    assert "добавьте новую версию с новой датой" in page
