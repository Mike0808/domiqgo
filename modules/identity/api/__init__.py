"""Публичный API Identity — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `GrantPrivacyConsent` | `grant_privacy_consent` |
| `HasCurrentConsent(account_id)` | `has_current_consent` |
| `IssueLinkCode` | `issue_link_code` |
| `RedeemLinkCode` | `redeem_link_code` |
| `LinkExternalIdentity` (решение) | `admit_external_login` |
| `ListLinkedProviders(account_id)` | `list_linked_providers` |
| `GetAccount(account_id)` | `get_account` |
| `CreateAccount` (тип) | `register_account` |

**Чего здесь пока нет.** `UnlinkExternalIdentity`, `ChangePassword`,
`SuspendAccount` и статус учётной записи — за пределами этапа C.
`CreateAccount` представлен половиной: имя входа и пароль заводит
стандартная админка Django, `register_account` записывает тип.

**Тип учётной записи хранит Identity.** Куда вести человека после входа,
решается раньше, чем кто-либо спросит про договоры; выводить тип из Tenancy
значило бы замкнуть цикл. Незарегистрированная запись получает тип мостом от
флага «персонал» — пока `CreateAccount` не появится в панели владельца.

**Редакция политики приходит снаружи.** Модуль не знает, какая редакция
считается текущей, — это вопрос текста политики, а не учётных записей.
Вызывающий передаёт её явно, и потому история согласий читается одинаково
через год после смены текста.

**Код привязки доказывает личность и только её.** `redeem_link_code`
возвращает учётную запись и останавливается: привязать чат к ней — дело
Notifications, а оркеструет обе команды интерфейсный слой бота (ADR-0017).

**Внешний вход: домен решает, allauth исполняет.** `admit_external_login`
отвечает, что делать с пришедшей внешней личностью (инварианты 1 и 2); саму
привязку и вход выполняет allauth — инфраструктура Identity, — а адаптер в
интерфейсном слое лишь переводит решение в ответ HTTP.
"""

from datetime import datetime

from ..application import commands, queries
from ..domain.account import Account, AccountType
from ..domain.consent import Consent
from ..domain.external_login import ExternalLoginDecision
from ..domain.link_code import InvalidLinkCode as InvalidLinkCodeError


def _repository():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def get_account(account_id: int) -> Account:
    """Учётная запись и её тип: владелец или жилец.

    Спрашивает интерфейсный слой после входа и при выдаче файлов; спросит
    Tenancy, заключая договор.
    """
    return queries.get_account(_repository(), account_id)


def has_current_consent(account_id: int, policy_version: str) -> bool:
    """Дано ли согласие на эту редакцию политики."""
    return queries.has_current_consent(_repository(), account_id, policy_version)


def consent_history(account_id: int) -> list[Consent]:
    """Все согласия учётной записи в порядке появления — для аудита 152-ФЗ."""
    return queries.consent_history(_repository(), account_id)


def admit_external_login(identity_known: bool, account_id: int | None,
                         policy_version: str) -> ExternalLoginDecision:
    """Что делать с внешней личностью, пришедшей от провайдера.

    `identity_known` — привязана ли она уже к какой-то записи; `account_id` —
    кто сейчас вошёл по паролю, если кто-то вошёл. Спрашивает адаптер входа
    через провайдера.
    """
    return queries.external_login_decision(
        _repository(), identity_known, account_id, policy_version)


def list_linked_providers(account_id: int) -> list[str]:
    """Идентификаторы провайдеров, привязанных к учётной записи."""
    return queries.linked_providers(_repository(), account_id)


# ------------------------------------------------------------------- команды

def register_account(account_id: int, type: AccountType) -> None:
    """Записать тип учётной записи в реестр; прежняя запись замещается."""
    commands.register_account(_repository(), account_id, type)


def grant_privacy_consent(account_id: int, policy_version: str,
                          at: datetime) -> None:
    """Зафиксировать согласие на обработку персональных данных.

    Прежние согласия не трогаются: каждое — отдельный факт, и журнал, умеющий
    менять прошлое, доказательством не является.
    """
    commands.grant_privacy_consent(_repository(), account_id, policy_version, at)


def issue_link_code(account_id: int) -> str:
    """Выпустить одноразовый код привязки. Прежний код записи, если был,
    перестаёт действовать."""
    return commands.issue_link_code(_repository(), account_id)


def redeem_link_code(code: str | None) -> int:
    """Погасить код и узнать, чьей учётной записи он принадлежал.

    Поднимает `InvalidLinkCodeError`, если код пуст или никому не принадлежит.
    Повторное предъявление того же кода — та же ошибка: код одноразовый.
    """
    return commands.redeem_link_code(_repository(), code)


__all__ = [
    "Account", "AccountType", "Consent", "ExternalLoginDecision",
    "InvalidLinkCodeError",
    "get_account", "has_current_consent", "consent_history",
    "admit_external_login", "list_linked_providers",
    "register_account", "grant_privacy_consent", "issue_link_code",
    "redeem_link_code",
]
