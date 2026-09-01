"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий и единственное
место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import datetime

from bus import publish

from ..domain.account import AccountType
from ..domain.link_code import InvalidLinkCode, LinkCode, presented
from ..events import PrivacyConsentGranted
from .ports import AccountRegistry, ConsentRepository, LinkCodeRepository


def register_account(registry: AccountRegistry, account_id: int,
                     type: AccountType) -> None:
    """Записать тип учётной записи в реестр.

    Это половина `CreateAccount`: имя входа и пароль заводит стандартная
    админка Django, а здесь фиксируется то, чего у `auth.User` нет. События
    `AccountCreated` нет намеренно — запись уже существовала, и объявлять её
    созданной значило бы лгать журналу шины.
    """
    registry.register(account_id, type)


def grant_privacy_consent(repository: ConsentRepository, account_id: int,
                          policy_version: str, at: datetime) -> None:
    """Зафиксировать согласие на текущую редакцию политики.

    Момент передаётся снаружи, а не берётся модулем: «сейчас» — понятие
    интерфейса, а перенос прежних согласий обязан сохранить их собственные
    даты, а не проставить дату переноса.
    """
    journal = repository.load_journal(account_id)
    consent = journal.grant(policy_version, at)
    repository.append(account_id, consent.policy_version, consent.given_at)
    publish(PrivacyConsentGranted(
        account_id=account_id, policy_version=consent.policy_version,
        given_at=consent.given_at))


def issue_link_code(repository: LinkCodeRepository, account_id: int) -> str:
    """Выпустить код привязки; прежний код записи перестаёт действовать."""
    link_code = LinkCode.issue(account_id)
    repository.replace(link_code)
    return link_code.code


def redeem_link_code(repository: LinkCodeRepository, raw_code: str | None) -> int:
    """Погасить код и вернуть, чьей учётной записи он принадлежал.

    Код одноразовый (инвариант 5): гасится в том же вызове, в котором
    опознан. События нет — результат нужен вызывающему немедленно, и
    асинхронный сценарий тут ни к чему (спецификация, «Публикуемые события»).
    """
    link_code = repository.find(presented(raw_code))
    if link_code is None:
        raise InvalidLinkCode("Неверный код.")
    repository.discard(link_code)
    return link_code.account_id
