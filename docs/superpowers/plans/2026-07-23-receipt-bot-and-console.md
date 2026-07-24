# Receipt Bot + Approval Console — Implementation Plan (Plan 2A of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant pay and prove it by sending a receipt photo to a Telegram bot; the receipt attaches to their earliest unpaid statement, moves it to «на проверке», and the landlord confirms it in an admin approval console — flipping the statement to «оплачено».

**Architecture:** A platform-agnostic bot core (`process_message` / `handle_update`) talks only to a `MessengerAdapter` interface and to two ORM services — receipt **intake** and chat **linking**. The concrete `TelegramAdapter` wraps the Telegram Bot REST API with plain `requests`; a `MaxAdapter` stub conforms to the same interface for later. A secret-protected webhook view (prod) and a polling management command (dev) are the two delivery mechanisms. The admin console adds a pending-payments queue with receipt previews, confirm/reject actions, and file deletion.

**Tech Stack:** Django 5.1, `requests`, pytest + pytest-django. Builds on Plan 1 (`billing` app). Money/statement logic unchanged.

**Deferred to Plan 2B (not built here):** the tenant web receipt-upload page + «Мои чеки» list, and the concrete MAX adapter. Both reuse the intake service and adapter interface built here.

## Global Constraints

- Python **3.12+**, Django **5.1.x**. Same locale as Plan 1: `LANGUAGE_CODE='ru'`, `TIME_ZONE='Asia/Yekaterinburg'`.
- All bot replies and admin text in **Russian**.
- TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- Environment: Windows/PowerShell; the Bash tool is non-functional. A virtualenv exists at `.venv`; its activation does NOT persist between tool calls, so always invoke the interpreter explicitly: `.\.venv\Scripts\python.exe -m pytest ...` and `.\.venv\Scripts\python.exe manage.py ...`. Commit with `git add <exact files>` (never `git add -A`; unrelated scratch dirs exist). If a commit fails on git identity, prefix `git -c user.name="local-rent" -c user.email="haighrain@gmail.com" commit ...`.
- **Receipt intake targets the EARLIEST `MonthlyStatement` whose status is `unpaid`.** If none exists, raise `NoUnpaidStatementError`.
- **Status transitions:** attaching a receipt → statement `pending`, payment `pending`. Confirm → payment `confirmed`, statement `paid`. Reject → payment `rejected`, statement back to `unpaid` **only if no other `pending` payment remains** on it.
- Webhook is **secret-protected**: Telegram's `X-Telegram-Bot-Api-Secret-Token` header must equal `settings.TELEGRAM_WEBHOOK_SECRET`; reject otherwise.
- The bot never trusts a receipt as proof of payment — it only moves the statement to `pending`; a human confirm is always required.

---

## File Structure

```
billing/
  models.py                      # + Payment model (append)
  admin.py                       # + PaymentAdmin, PaymentInline, confirm/reject actions (append)
  urls.py                        # + telegram webhook route (append)
  webhooks.py                    # NEW: secret-checked webhook view
  services/
    intake.py                    # NEW: attach_receipt, confirm_payment, reject_payment
    linking.py                   # NEW: generate_link_code, link_chat
    bot.py                       # NEW: process_message / handle_update (platform-agnostic core)
  messengers/
    __init__.py                  # NEW
    base.py                      # NEW: MessengerAdapter ABC + IncomingMessage
    telegram.py                  # NEW: TelegramAdapter (REST)
    max.py                       # NEW: MaxAdapter stub (interface-conforming, deferred)
  management/
    __init__.py                  # NEW
    commands/
      __init__.py                # NEW
      run_telegram_polling.py    # NEW: dev delivery (getUpdates loop)
      set_telegram_webhook.py    # NEW: register prod webhook
  tests/
    fakes.py                     # NEW: FakeAdapter used across bot tests
    test_intake.py               # NEW
    test_linking.py              # NEW
    test_bot.py                  # NEW
    test_telegram_adapter.py     # NEW
    test_webhook.py              # NEW
    test_payment_admin.py        # NEW
config/settings.py               # + TELEGRAM_* settings (append)
requirements.txt                 # + requests
deploy/.env.example              # + TELEGRAM_* vars
```

**Responsibilities:** `bot.py` holds all routing logic and is fully testable with a `FakeAdapter` (no network). `intake.py`/`linking.py` are ORM services with no messenger knowledge. `messengers/` isolates all platform/network code behind one interface. `webhooks.py` + the two commands are thin delivery shells.

---

### Task 1: Payment model + migration

**Files:**
- Modify: `billing/models.py` (append `Payment`)
- Test: `billing/tests/test_payment.py`

**Interfaces:**
- Consumes: `MonthlyStatement` (Plan 1).
- Produces: `Payment` with `TELEGRAM/MAX/WEB` source constants, `PENDING/CONFIRMED/REJECTED` status constants, FK `statement` (related_name `payments`), `file`, `source`, `status` (default `PENDING`), `note`, `submitted_at`.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_payment.py`

```python
from datetime import date
from django.core.files.base import ContentFile
import pytest
from billing.models import Apartment, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

def _stmt():
    a = Apartment.objects.create(label="кв. 1")
    return MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

def test_payment_defaults_to_pending():
    p = Payment(statement=_stmt(), source=Payment.TELEGRAM)
    p.file.save("r.jpg", ContentFile(b"img"), save=True)
    assert p.status == Payment.PENDING
    assert p.statement.payments.count() == 1

def test_payment_source_choices_cover_all_channels():
    codes = {c for c, _ in Payment.SOURCE_CHOICES}
    assert codes == {Payment.TELEGRAM, Payment.MAX, Payment.WEB}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_payment.py -v`
Expected: FAIL with `ImportError` (Payment not defined).

- [ ] **Step 3: Append `Payment` to `billing/models.py`**

```python
def receipt_upload_path(instance, filename):
    return f"receipts/statement_{instance.statement_id}/{filename}"

class Payment(models.Model):
    TELEGRAM = "telegram"; MAX = "max"; WEB = "web"
    SOURCE_CHOICES = [(TELEGRAM, "Telegram"), (MAX, "MAX"), (WEB, "Веб")]
    PENDING = "pending"; CONFIRMED = "confirmed"; REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "На проверке"), (CONFIRMED, "Подтверждён"), (REJECTED, "Отклонён"),
    ]

    statement = models.ForeignKey(MonthlyStatement, on_delete=models.CASCADE,
                                  related_name="payments")
    file = models.FileField("Чек", upload_to=receipt_upload_path)
    source = models.CharField("Источник", max_length=10, choices=SOURCE_CHOICES)
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=PENDING)
    note = models.CharField("Примечание", max_length=300, blank=True)
    submitted_at = models.DateTimeField("Получен", auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Платёж {self.statement} ({self.get_status_display()})"
```

- [ ] **Step 4: Make and apply the migration**

Run:
```powershell
.\.venv\Scripts\python.exe manage.py makemigrations billing
.\.venv\Scripts\python.exe manage.py migrate
```
Expected: one new migration (`0002_payment.py`) created and applied.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest billing/tests/test_payment.py -v`
Expected: both PASS.

- [ ] **Step 6: Commit**

```powershell
git add billing/models.py billing/migrations billing/tests/test_payment.py
git commit -m "feat: Payment model for receipts"
```

---

### Task 2: Receipt-intake service (TDD)

**Files:**
- Create: `billing/services/intake.py`
- Test: `billing/tests/test_intake.py`

**Interfaces:**
- Consumes: `MonthlyStatement`, `Payment` (Task 1).
- Produces:
  - `class NoUnpaidStatementError(Exception)`.
  - `def earliest_unpaid_statement(apartment) -> MonthlyStatement | None`.
  - `def attach_receipt(tenant, file, source, filename=None) -> Payment` — earliest unpaid statement → new `Payment` (status pending) → statement `pending`. Raises `NoUnpaidStatementError` if none. `file` is a Django `File`/`ContentFile`.
  - `def confirm_payment(payment) -> None` — payment `confirmed`, statement `paid`.
  - `def reject_payment(payment, note="") -> None` — payment `rejected`; statement → `unpaid` unless another `pending` payment remains.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_intake.py`

```python
from datetime import date
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.services.intake import (
    attach_receipt, confirm_payment, reject_payment,
    earliest_unpaid_statement, NoUnpaidStatementError,
)

pytestmark = pytest.mark.django_db

def _tenant():
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    return Tenant.objects.create(user=u, apartment=a, full_name="Т"), a

def _receipt():
    return ContentFile(b"img", name="r.jpg")

def test_attach_targets_earliest_unpaid_and_sets_pending():
    tenant, a = _tenant()
    june = MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="unpaid")
    july = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    assert payment.statement == june                 # earliest
    june.refresh_from_db(); july.refresh_from_db()
    assert june.status == MonthlyStatement.PENDING
    assert july.status == MonthlyStatement.UNPAID
    assert payment.status == Payment.PENDING
    assert payment.file.read() == b"img"

def test_attach_skips_pending_and_paid():
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 5, 1), status="paid")
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="pending")
    unpaid = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.WEB)
    assert payment.statement == unpaid

def test_attach_raises_when_nothing_unpaid():
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="paid")
    with pytest.raises(NoUnpaidStatementError):
        attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)

def test_confirm_sets_paid():
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    confirm_payment(payment)
    payment.refresh_from_db(); payment.statement.refresh_from_db()
    assert payment.status == Payment.CONFIRMED
    assert payment.statement.status == MonthlyStatement.PAID

def test_reject_reverts_to_unpaid_when_no_other_pending():
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    reject_payment(payment, note="нечитаемый чек")
    payment.refresh_from_db(); payment.statement.refresh_from_db()
    assert payment.status == Payment.REJECTED
    assert payment.note == "нечитаемый чек"
    assert payment.statement.status == MonthlyStatement.UNPAID

def test_reject_keeps_pending_when_another_pending_exists():
    tenant, a = _tenant()
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    p1 = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    # a second pending payment on the same statement
    p2 = Payment.objects.create(statement=stmt, source=Payment.WEB, status=Payment.PENDING)
    reject_payment(p1)
    stmt.refresh_from_db()
    assert stmt.status == MonthlyStatement.PENDING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: billing.services.intake`.

- [ ] **Step 3: Implement `billing/services/intake.py`**

```python
from django.db import transaction
from ..models import MonthlyStatement, Payment

class NoUnpaidStatementError(Exception):
    """No statement with status 'unpaid' to attach a receipt to."""

def earliest_unpaid_statement(apartment):
    return (MonthlyStatement.objects
            .filter(apartment=apartment, status=MonthlyStatement.UNPAID)
            .order_by("period").first())

@transaction.atomic
def attach_receipt(tenant, file, source, filename=None):
    stmt = earliest_unpaid_statement(tenant.apartment)
    if stmt is None:
        raise NoUnpaidStatementError("Нет неоплаченных начислений.")
    payment = Payment(statement=stmt, source=source)
    payment.file.save(filename or getattr(file, "name", "receipt"), file, save=False)
    payment.save()
    stmt.status = MonthlyStatement.PENDING
    stmt.save(update_fields=["status"])
    return payment

@transaction.atomic
def confirm_payment(payment):
    payment.status = Payment.CONFIRMED
    payment.save(update_fields=["status"])
    stmt = payment.statement
    stmt.status = MonthlyStatement.PAID
    stmt.save(update_fields=["status"])

@transaction.atomic
def reject_payment(payment, note=""):
    payment.status = Payment.REJECTED
    fields = ["status"]
    if note:
        payment.note = note
        fields.append("note")
    payment.save(update_fields=fields)
    stmt = payment.statement
    if not stmt.payments.filter(status=Payment.PENDING).exists():
        stmt.status = MonthlyStatement.UNPAID
        stmt.save(update_fields=["status"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_intake.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```powershell
git add billing/services/intake.py billing/tests/test_intake.py
git commit -m "feat: receipt-intake service (attach/confirm/reject)"
```

---

### Task 3: Tenant↔chat linking service (TDD)

**Files:**
- Create: `billing/services/linking.py`
- Test: `billing/tests/test_linking.py`

**Interfaces:**
- Consumes: `Tenant` (Plan 1 fields `messenger_platform`, `messenger_chat_id`, `link_code`).
- Produces:
  - `def generate_link_code(tenant) -> str` — sets and returns a fresh non-empty code.
  - `class InvalidLinkCodeError(Exception)`.
  - `def link_chat(platform, chat_id, code) -> Tenant` — binds chat to the tenant with that code; single-use (clears `link_code`). Raises `InvalidLinkCodeError` on empty/unknown code.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_linking.py`

```python
from django.contrib.auth.models import User
import pytest
from billing.models import Apartment, Tenant
from billing.services.linking import (
    generate_link_code, link_chat, InvalidLinkCodeError,
)

pytestmark = pytest.mark.django_db

def _tenant(username="t"):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user(username, password="x")
    return Tenant.objects.create(user=u, apartment=a, full_name="Т")

def test_generate_code_is_non_empty_and_saved():
    t = _tenant()
    code = generate_link_code(t)
    assert code
    t.refresh_from_db()
    assert t.link_code == code

def test_link_binds_chat_and_is_single_use():
    t = _tenant()
    code = generate_link_code(t)
    linked = link_chat("telegram", 12345, code)
    assert linked.pk == t.pk
    t.refresh_from_db()
    assert t.messenger_platform == "telegram"
    assert t.messenger_chat_id == "12345"
    assert t.link_code == ""                      # consumed
    with pytest.raises(InvalidLinkCodeError):     # cannot reuse
        link_chat("telegram", 999, code)

def test_empty_code_rejected_and_matches_nobody():
    _tenant("a")   # has blank link_code by default
    with pytest.raises(InvalidLinkCodeError):
        link_chat("telegram", 1, "")

def test_unknown_code_rejected():
    with pytest.raises(InvalidLinkCodeError):
        link_chat("telegram", 1, "does-not-exist")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_linking.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `billing/services/linking.py`**

```python
import secrets
from ..models import Tenant

class InvalidLinkCodeError(Exception):
    """The supplied link code was empty or matched no tenant."""

def generate_link_code(tenant):
    code = secrets.token_urlsafe(8)
    tenant.link_code = code
    tenant.save(update_fields=["link_code"])
    return code

def link_chat(platform, chat_id, code):
    code = (code or "").strip()
    if not code:
        raise InvalidLinkCodeError("Неверный код.")
    tenant = Tenant.objects.filter(link_code=code).first()
    if tenant is None:
        raise InvalidLinkCodeError("Неверный код.")
    tenant.messenger_platform = platform
    tenant.messenger_chat_id = str(chat_id)
    tenant.link_code = ""
    tenant.save(update_fields=["messenger_platform", "messenger_chat_id", "link_code"])
    return tenant
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_linking.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```powershell
git add billing/services/linking.py billing/tests/test_linking.py
git commit -m "feat: tenant-chat linking service with single-use codes"
```

---

### Task 4: MessengerAdapter interface + MAX stub

**Files:**
- Create: `billing/messengers/__init__.py`, `billing/messengers/base.py`, `billing/messengers/max.py`
- Test: `billing/tests/test_adapter_interface.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class IncomingMessage` with fields `platform: str`, `chat_id: str`, `text: str = ""`, `file_id: str = ""`, `file_name: str = ""`.
  - `class MessengerAdapter(ABC)` with class attr `platform` and abstract methods `parse_update(raw_update) -> IncomingMessage | None`, `download_file(file_id) -> bytes`, `send_message(chat_id, text) -> None`, `set_webhook(url) -> None`.
  - `class MaxAdapter(MessengerAdapter)` — `platform = "max"`, all methods raise `NotImplementedError` (deferred; documents the seam).

- [ ] **Step 1: Write failing tests** — `billing/tests/test_adapter_interface.py`

```python
import pytest
from billing.messengers.base import MessengerAdapter, IncomingMessage
from billing.messengers.max import MaxAdapter

def test_incoming_message_defaults():
    m = IncomingMessage(platform="telegram", chat_id="1")
    assert m.text == "" and m.file_id == "" and m.file_name == ""

def test_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MessengerAdapter()

def test_max_adapter_conforms_but_is_deferred():
    a = MaxAdapter()
    assert a.platform == "max"
    with pytest.raises(NotImplementedError):
        a.send_message("1", "hi")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_adapter_interface.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the files**

`billing/messengers/__init__.py`:
```python
```
(empty file)

`billing/messengers/base.py`:
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class IncomingMessage:
    platform: str
    chat_id: str
    text: str = ""
    file_id: str = ""
    file_name: str = ""

class MessengerAdapter(ABC):
    platform: str = ""

    @abstractmethod
    def parse_update(self, raw_update: dict):
        """Return an IncomingMessage, or None if the update is irrelevant."""

    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """Fetch the bytes of a file the user sent."""

    @abstractmethod
    def send_message(self, chat_id: str, text: str) -> None:
        """Send a plain-text reply to the chat."""

    @abstractmethod
    def set_webhook(self, url: str) -> None:
        """Register the given URL to receive updates."""
```

`billing/messengers/max.py`:
```python
from .base import MessengerAdapter

class MaxAdapter(MessengerAdapter):
    """Adapter for the MAX messenger (VK). Deferred to Plan 2B.

    MAX exposes a REST Bot API at platform-api.max.ru (webhook + long-polling),
    but publishing a bot requires a verified Russian legal entity (since Aug 2025),
    so this adapter is intentionally left unimplemented. It exists to prove the
    MessengerAdapter seam supports a second platform with no changes to bot.py.
    """
    platform = "max"

    def parse_update(self, raw_update):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def download_file(self, file_id):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def send_message(self, chat_id, text):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")

    def set_webhook(self, url):
        raise NotImplementedError("MAX adapter is deferred to Plan 2B.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_adapter_interface.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add billing/messengers billing/tests/test_adapter_interface.py
git commit -m "feat: MessengerAdapter interface + deferred MAX stub"
```

---

### Task 5: Bot dispatch core (TDD) — the heart

**Files:**
- Create: `billing/services/bot.py`, `billing/tests/fakes.py`
- Test: `billing/tests/test_bot.py`

**Interfaces:**
- Consumes: `attach_receipt`/`NoUnpaidStatementError` (Task 2), `link_chat`/`InvalidLinkCodeError` (Task 3), `MessengerAdapter`/`IncomingMessage` (Task 4), `Tenant`.
- Produces:
  - `def process_message(adapter, msg: IncomingMessage) -> str` — routing; returns the reply text.
  - `def handle_update(adapter, raw_update) -> None` — `adapter.parse_update` → `process_message` → `adapter.send_message`.
  - `FakeAdapter` in `billing/tests/fakes.py` (records `sent`, returns canned parse/file) for this and later tasks.

- [ ] **Step 1: Write the FakeAdapter helper** — `billing/tests/fakes.py`

```python
from billing.messengers.base import MessengerAdapter

class FakeAdapter(MessengerAdapter):
    platform = "telegram"

    def __init__(self, parsed=None, file_bytes=b"img"):
        self._parsed = parsed
        self._file_bytes = file_bytes
        self.sent = []          # list of (chat_id, text)

    def parse_update(self, raw_update):
        # In handle_update tests, `parsed` is what parse_update yields.
        return self._parsed

    def download_file(self, file_id):
        return self._file_bytes

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    def set_webhook(self, url):
        pass
```

- [ ] **Step 2: Write failing tests** — `billing/tests/test_bot.py`

```python
from datetime import date
from django.contrib.auth.models import User
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.messengers.base import IncomingMessage
from billing.services.bot import process_message, handle_update
from billing.services.linking import generate_link_code
from billing.tests.fakes import FakeAdapter

pytestmark = pytest.mark.django_db

def _tenant(chat_id=None):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    t = Tenant.objects.create(user=u, apartment=a, full_name="Иванов")
    if chat_id is not None:
        t.messenger_platform = "telegram"; t.messenger_chat_id = str(chat_id); t.save()
    return t, a

def _msg(**kw):
    kw.setdefault("platform", "telegram")
    kw.setdefault("chat_id", "555")
    return IncomingMessage(**kw)

def test_start_with_valid_code_links_chat():
    t, _ = _tenant()
    code = generate_link_code(t)
    reply = process_message(FakeAdapter(), _msg(text=f"/start {code}"))
    t.refresh_from_db()
    assert t.messenger_chat_id == "555"
    assert "привязан" in reply.lower()

def test_start_without_code_asks_for_it():
    reply = process_message(FakeAdapter(), _msg(text="/start"))
    assert "код" in reply.lower()

def test_start_with_bad_code_reports_error():
    reply = process_message(FakeAdapter(), _msg(text="/start nope"))
    assert "неверный код" in reply.lower()

def test_photo_from_linked_tenant_attaches_receipt():
    t, a = _tenant(chat_id=555)
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    adapter = FakeAdapter(file_bytes=b"receipt-bytes")
    reply = process_message(adapter, _msg(file_id="photo123"))
    assert "на проверку" in reply.lower()
    payment = Payment.objects.get()
    assert payment.statement.status == MonthlyStatement.PENDING
    assert payment.file.read() == b"receipt-bytes"
    assert payment.source == "telegram"

def test_photo_from_unlinked_chat_is_refused():
    reply = process_message(FakeAdapter(), _msg(file_id="photo123"))
    assert "привяжите" in reply.lower()
    assert Payment.objects.count() == 0

def test_photo_with_no_unpaid_statement_is_reported():
    t, a = _tenant(chat_id=555)
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="paid")
    reply = process_message(FakeAdapter(), _msg(file_id="photo123"))
    assert "нет неоплаченных" in reply.lower()

def test_plain_text_from_linked_tenant_gets_help():
    _tenant(chat_id=555)
    reply = process_message(FakeAdapter(), _msg(text="привет"))
    assert "чек" in reply.lower()

def test_handle_update_parses_then_sends():
    _tenant(chat_id=555)
    adapter = FakeAdapter(parsed=_msg(text="привет"))
    handle_update(adapter, {"any": "json"})
    assert len(adapter.sent) == 1
    assert adapter.sent[0][0] == "555"

def test_handle_update_ignores_irrelevant_update():
    adapter = FakeAdapter(parsed=None)
    handle_update(adapter, {"channel_post": {}})
    assert adapter.sent == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest billing/tests/test_bot.py -v`
Expected: FAIL with `ModuleNotFoundError: billing.services.bot`.

- [ ] **Step 4: Implement `billing/services/bot.py`**

```python
import re
from django.core.files.base import ContentFile
from django.utils import timezone
from ..models import Tenant
from .intake import attach_receipt, NoUnpaidStatementError
from .linking import link_chat, InvalidLinkCodeError

MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
HELP = "Отправьте фото чека об оплате. Чтобы привязать аккаунт: /start <код>."
START_RE = re.compile(r"^/start(?:\s+(?P<code>\S+))?")

def _period_ru(d):
    return f"{MONTHS_RU[d.month]} {d.year}"

def _find_tenant(msg):
    return Tenant.objects.filter(
        messenger_platform=msg.platform, messenger_chat_id=str(msg.chat_id)
    ).first()

def process_message(adapter, msg) -> str:
    text = msg.text or ""
    m = START_RE.match(text)
    if m:
        code = m.group("code")
        if not code:
            return "Укажите код: /start <код>. Код выдаёт арендодатель."
        try:
            tenant = link_chat(msg.platform, msg.chat_id, code)
        except InvalidLinkCodeError:
            return "Неверный код. Обратитесь к арендодателю."
        return f"Аккаунт привязан: {tenant}. Пришлите фото чека для оплаты."

    tenant = _find_tenant(msg)
    if msg.file_id:
        if tenant is None:
            return "Сначала привяжите аккаунт командой /start <код>."
        data = adapter.download_file(msg.file_id)
        name = msg.file_name or f"{msg.platform}_{timezone.now():%Y%m%d%H%M%S}.jpg"
        try:
            payment = attach_receipt(tenant, ContentFile(data, name=name), source=msg.platform)
        except NoUnpaidStatementError:
            return "Нет неоплаченных начислений."
        return (f"Чек получен, начисление за {_period_ru(payment.statement.period)} "
                f"отправлено на проверку.")

    if tenant is None:
        return "Здравствуйте! Привяжите аккаунт командой /start <код> (код выдаёт арендодатель)."
    return HELP

def handle_update(adapter, raw_update) -> None:
    msg = adapter.parse_update(raw_update)
    if msg is None:
        return
    reply = process_message(adapter, msg)
    if reply:
        adapter.send_message(msg.chat_id, reply)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest billing/tests/test_bot.py -v`
Expected: all 9 PASS.

- [ ] **Step 6: Commit**

```powershell
git add billing/services/bot.py billing/tests/fakes.py billing/tests/test_bot.py
git commit -m "feat: platform-agnostic bot dispatch core"
```

---

### Task 6: TelegramAdapter (REST) + settings + requirements

**Files:**
- Create: `billing/messengers/telegram.py`
- Modify: `config/settings.py` (append), `requirements.txt` (append `requests`), `deploy/.env.example` (append)
- Test: `billing/tests/test_telegram_adapter.py`

**Interfaces:**
- Consumes: `MessengerAdapter`/`IncomingMessage` (Task 4), `settings.TELEGRAM_BOT_TOKEN`, `settings.TELEGRAM_WEBHOOK_SECRET`.
- Produces: `class TelegramAdapter(MessengerAdapter)` with `platform="telegram"`, `__init__(token=None)`, and the four methods over the Telegram Bot API. `parse_update` picks the largest `photo` size or a `document`.

- [ ] **Step 1: Add `requests` to `requirements.txt`**

Append the line:
```
requests==2.*
```
Then install: `.\.venv\Scripts\python.exe -m pip install "requests==2.*"`

- [ ] **Step 2: Write failing tests** — `billing/tests/test_telegram_adapter.py`

```python
import billing.messengers.telegram as tg
from billing.messengers.telegram import TelegramAdapter

def test_parse_photo_picks_largest_size():
    update = {"message": {"chat": {"id": 42}, "photo": [
        {"file_id": "small"}, {"file_id": "big"}]}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.chat_id == "42"
    assert msg.file_id == "big"

def test_parse_document_keeps_filename():
    update = {"message": {"chat": {"id": 7},
              "document": {"file_id": "doc1", "file_name": "check.pdf"}}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.file_id == "doc1"
    assert msg.file_name == "check.pdf"

def test_parse_text_message():
    update = {"message": {"chat": {"id": 7}, "text": "/start abc"}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.text == "/start abc"
    assert msg.file_id == ""

def test_parse_non_message_update_returns_none():
    assert TelegramAdapter(token="T").parse_update({"channel_post": {}}) is None

def test_send_message_posts_to_api(monkeypatch):
    calls = {}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {}
    def fake_post(url, json=None, timeout=None):
        calls["url"] = url; calls["json"] = json
        return Resp()
    monkeypatch.setattr(tg.requests, "post", fake_post)
    TelegramAdapter(token="T").send_message("42", "привет")
    assert calls["url"].endswith("/botT/sendMessage")
    assert calls["json"] == {"chat_id": "42", "text": "привет"}

def test_download_file_two_step(monkeypatch):
    class Resp:
        def __init__(self, js=None, content=b""): self._js = js; self.content = content
        def raise_for_status(self): pass
        def json(self): return self._js
    def fake_get(url, params=None, timeout=None):
        if "getFile" in url:
            return Resp(js={"result": {"file_path": "photos/x.jpg"}})
        return Resp(content=b"IMG")
    monkeypatch.setattr(tg.requests, "get", fake_get)
    data = TelegramAdapter(token="T").download_file("fid")
    assert data == b"IMG"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest billing/tests/test_telegram_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: billing.messengers.telegram`.

- [ ] **Step 4: Implement `billing/messengers/telegram.py`**

```python
import requests
from django.conf import settings
from .base import MessengerAdapter, IncomingMessage

API = "https://api.telegram.org"

class TelegramAdapter(MessengerAdapter):
    platform = "telegram"

    def __init__(self, token=None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN

    def _method(self, name):
        return f"{API}/bot{self.token}/{name}"

    def parse_update(self, raw_update):
        message = raw_update.get("message") or raw_update.get("edited_message")
        if not message:
            return None
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "")
        file_id = ""
        file_name = ""
        if message.get("photo"):
            file_id = message["photo"][-1]["file_id"]      # largest size last
        elif message.get("document"):
            file_id = message["document"]["file_id"]
            file_name = message["document"].get("file_name", "")
        return IncomingMessage(platform=self.platform, chat_id=chat_id,
                               text=text, file_id=file_id, file_name=file_name)

    def download_file(self, file_id):
        r = requests.get(self._method("getFile"), params={"file_id": file_id}, timeout=30)
        r.raise_for_status()
        path = r.json()["result"]["file_path"]
        fr = requests.get(f"{API}/file/bot{self.token}/{path}", timeout=60)
        fr.raise_for_status()
        return fr.content

    def send_message(self, chat_id, text):
        r = requests.post(self._method("sendMessage"),
                          json={"chat_id": chat_id, "text": text}, timeout=30)
        r.raise_for_status()

    def set_webhook(self, url):
        r = requests.post(self._method("setWebhook"),
                          json={"url": url, "secret_token": settings.TELEGRAM_WEBHOOK_SECRET},
                          timeout=30)
        r.raise_for_status()
```

- [ ] **Step 5: Append settings** to `config/settings.py` (after the reverse-proxy block from the deploy work):

```python
# Messenger bot (Plan 2)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
```

- [ ] **Step 6: Append to `deploy/.env.example`**

```
# Telegram receipt bot (Plan 2). Token from @BotFather; secret is any long random string.
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
```

- [ ] **Step 7: Run tests + full suite**

Run:
```powershell
pytest billing/tests/test_telegram_adapter.py -v
pytest -v
```
Expected: adapter tests (6) PASS; full suite PASSES with no regressions.

- [ ] **Step 8: Commit**

```powershell
git add billing/messengers/telegram.py config/settings.py requirements.txt deploy/.env.example billing/tests/test_telegram_adapter.py
git commit -m "feat: TelegramAdapter over Bot REST API + settings"
```

---

### Task 7: Webhook view + URL + polling/webhook commands

**Files:**
- Create: `billing/webhooks.py`, `billing/management/__init__.py`, `billing/management/commands/__init__.py`, `billing/management/commands/run_telegram_polling.py`, `billing/management/commands/set_telegram_webhook.py`
- Modify: `billing/urls.py` (append route)
- Test: `billing/tests/test_webhook.py`

**Interfaces:**
- Consumes: `TelegramAdapter` (Task 6), `handle_update` (Task 5), `settings.TELEGRAM_WEBHOOK_SECRET`.
- Produces: `telegram_webhook(request)` view (name `telegram_webhook`, path `bot/telegram/webhook/`); `poll_once(adapter, offset) -> int` helper in the polling command.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_webhook.py`

```python
import json
from datetime import date
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment

pytestmark = pytest.mark.django_db

WEBHOOK = "/bot/telegram/webhook/"

def _linked_tenant(chat_id=555):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    Tenant.objects.create(user=u, apartment=a, full_name="Иванов",
                          messenger_platform="telegram", messenger_chat_id=str(chat_id))
    return a

def test_webhook_rejects_missing_secret(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="{}", content_type="application/json")
    assert resp.status_code == 403

def test_webhook_rejects_wrong_secret(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="{}", content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="nope")
    assert resp.status_code == 403

def test_webhook_processes_text_update(settings, monkeypatch):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    _linked_tenant(555)
    # Don't hit the network on the outbound reply.
    import billing.messengers.telegram as tg
    sent = {}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {}
    monkeypatch.setattr(tg.requests, "post",
                        lambda url, json=None, timeout=None: sent.update(json or {}) or Resp())
    body = json.dumps({"message": {"chat": {"id": 555}, "text": "привет"}})
    resp = Client().post(WEBHOOK, data=body, content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
    assert resp.status_code == 200
    assert sent.get("chat_id") == "555"          # a reply was sent to this chat

def test_webhook_bad_json_returns_400(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    resp = Client().post(WEBHOOK, data="not-json", content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_webhook.py -v`
Expected: FAIL (404 — route/view missing).

- [ ] **Step 3: Implement `billing/webhooks.py`**

```python
import json
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from .messengers.telegram import TelegramAdapter
from .services.bot import handle_update

@csrf_exempt
def telegram_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.TELEGRAM_WEBHOOK_SECRET or secret != settings.TELEGRAM_WEBHOOK_SECRET:
        return HttpResponseForbidden("bad secret")
    try:
        raw = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    handle_update(TelegramAdapter(), raw)
    return HttpResponse("ok")
```

- [ ] **Step 4: Append the route** in `billing/urls.py`

Add the import and the path (place it before the `""` current_month route):
```python
from .webhooks import telegram_webhook
```
and inside `urlpatterns`, add:
```python
    path("bot/telegram/webhook/", telegram_webhook, name="telegram_webhook"),
```

- [ ] **Step 5: Implement the polling command** — `billing/management/commands/run_telegram_polling.py`

```python
import time
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from billing.messengers.telegram import TelegramAdapter, API
from billing.services.bot import handle_update

def poll_once(adapter, offset):
    """Fetch one batch of updates, dispatch each, return the next offset."""
    r = requests.get(f"{API}/bot{adapter.token}/getUpdates",
                     params={"offset": offset, "timeout": 25}, timeout=30)
    r.raise_for_status()
    updates = r.json().get("result", [])
    for update in updates:
        handle_update(adapter, update)
        offset = update["update_id"] + 1
    return offset

class Command(BaseCommand):
    help = "Poll Telegram for updates (development delivery)."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stderr.write("TELEGRAM_BOT_TOKEN is not set.")
            return
        adapter = TelegramAdapter()
        offset = 0
        self.stdout.write("Polling Telegram (Ctrl+C to stop)...")
        while True:
            try:
                offset = poll_once(adapter, offset)
            except requests.RequestException as exc:
                self.stderr.write(f"poll error: {exc}")
                time.sleep(3)
```

- [ ] **Step 6: Implement the webhook-registration command** — `billing/management/commands/set_telegram_webhook.py`

```python
from django.core.management.base import BaseCommand, CommandError
from billing.messengers.telegram import TelegramAdapter

class Command(BaseCommand):
    help = "Register the Telegram webhook URL (production delivery)."

    def add_arguments(self, parser):
        parser.add_argument("url", help="Public HTTPS URL, e.g. "
                                        "https://domiq-ufa.ru/bot/telegram/webhook/")

    def handle(self, *args, **options):
        try:
            TelegramAdapter().set_webhook(options["url"])
        except Exception as exc:  # noqa: BLE001 - surface any API error to the operator
            raise CommandError(f"setWebhook failed: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Webhook set: {options['url']}"))
```

- [ ] **Step 7: Create the empty package files**

`billing/management/__init__.py` and `billing/management/commands/__init__.py` — both empty.

- [ ] **Step 8: Run tests + full suite**

Run:
```powershell
pytest billing/tests/test_webhook.py -v
pytest -v
```
Expected: webhook tests (4) PASS; full suite PASSES.

- [ ] **Step 9: Commit**

```powershell
git add billing/webhooks.py billing/urls.py billing/management billing/tests/test_webhook.py
git commit -m "feat: secret-checked webhook + polling/webhook management commands"
```

---

### Task 8: Admin approval console

**Files:**
- Modify: `billing/admin.py` (append)
- Test: `billing/tests/test_payment_admin.py`

**Interfaces:**
- Consumes: `Payment` (Task 1), `confirm_payment`/`reject_payment` (Task 2), `MonthlyStatement`.
- Produces: `PaymentAdmin` (pending queue via `list_filter`, receipt `preview`, `confirm_payments`/`reject_payments` actions, file-deleting `delete_model`/`delete_queryset`); `PaymentInline` on `MonthlyStatementAdmin`.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_payment_admin.py`

```python
from datetime import date
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.services.intake import attach_receipt

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_client():
    User.objects.create_superuser("boss", "b@e.com", "pass12345")
    c = Client(); c.login(username="boss", password="pass12345")
    return c

def _pending_payment():
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    t = Tenant.objects.create(user=u, apartment=a, full_name="Т")
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    return attach_receipt(t, ContentFile(b"img", name="r.jpg"), source=Payment.TELEGRAM)

def test_payment_changelist_loads(admin_client):
    _pending_payment()
    assert admin_client.get("/admin/billing/payment/").status_code == 200

def test_confirm_action_marks_paid(admin_client):
    p = _pending_payment()
    admin_client.post("/admin/billing/payment/", {
        "action": "confirm_payments", "_selected_action": [str(p.pk)]})
    p.refresh_from_db(); p.statement.refresh_from_db()
    assert p.status == Payment.CONFIRMED
    assert p.statement.status == MonthlyStatement.PAID

def test_reject_action_reverts_to_unpaid(admin_client):
    p = _pending_payment()
    admin_client.post("/admin/billing/payment/", {
        "action": "reject_payments", "_selected_action": [str(p.pk)]})
    p.refresh_from_db(); p.statement.refresh_from_db()
    assert p.status == Payment.REJECTED
    assert p.statement.status == MonthlyStatement.UNPAID

def test_delete_payment_removes_file_and_reverts_status(admin_client):
    import os
    p = _pending_payment()
    path = p.file.path
    assert os.path.exists(path)
    p.statement.refresh_from_db()
    assert p.statement.status == MonthlyStatement.PENDING
    # Django admin's single-object delete confirmation calls delete_model().
    admin_client.post(f"/admin/billing/payment/{p.pk}/delete/", {"post": "yes"})
    assert not Payment.objects.filter(pk=p.pk).exists()
    assert not os.path.exists(path)
    assert MonthlyStatement.objects.get().status == MonthlyStatement.UNPAID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_payment_admin.py -v`
Expected: FAIL (Payment not registered → 404 / assertion failures).

- [ ] **Step 3: Append to `billing/admin.py`**

Add imports at the top (alongside existing ones):
```python
from django.contrib import messages
from django.utils.html import format_html
from .models import Payment
from .services.intake import confirm_payment, reject_payment
```

Then append:
```python
@admin.action(description="Подтвердить оплату")
def confirm_payments(modeladmin, request, queryset):
    n = 0
    for p in queryset.filter(status=Payment.PENDING):
        confirm_payment(p); n += 1
    modeladmin.message_user(request, f"Подтверждено платежей: {n}.")

@admin.action(description="Отклонить платёж")
def reject_payments(modeladmin, request, queryset):
    n = 0
    for p in queryset.exclude(status=Payment.CONFIRMED):
        reject_payment(p); n += 1
    modeladmin.message_user(request, f"Отклонено платежей: {n}.", level=messages.WARNING)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("statement", "source", "status", "submitted_at", "preview")
    list_filter = ("status", "source")
    date_hierarchy = "submitted_at"
    readonly_fields = ("preview", "submitted_at")
    actions = [confirm_payments, reject_payments]

    @admin.display(description="Чек")
    def preview(self, obj):
        if not obj.file:
            return "—"
        url = obj.file.url
        if url.lower().endswith(".pdf"):
            return format_html('<a href="{}" target="_blank">PDF-чек</a>', url)
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-height:120px"></a>', url, url)

    def _delete_with_file(self, payment):
        payment.file.delete(save=False)
        stmt = payment.statement
        payment.delete()
        if (stmt.status == MonthlyStatement.PENDING
                and not stmt.payments.filter(status=Payment.PENDING).exists()):
            stmt.status = MonthlyStatement.UNPAID
            stmt.save(update_fields=["status"])

    def delete_model(self, request, obj):
        self._delete_with_file(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._delete_with_file(obj)

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("source", "status", "submitted_at")
```

Finally, wire the inline into the existing `MonthlyStatementAdmin` by adding to its class body:
```python
    inlines = [PaymentInline]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_payment_admin.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: every test across Plan 1 + Plan 2 PASSES.

- [ ] **Step 6: Commit**

```powershell
git add billing/admin.py billing/tests/test_payment_admin.py
git commit -m "feat: admin approval console — pending queue, confirm/reject, receipt preview, file delete"
```

---

## Definition of Done (Plan 2A)

- A tenant linked via `/start <код>` can send a receipt photo/PDF to the Telegram bot; it attaches to their earliest unpaid statement, which moves to «на проверке», and the tenant gets a Russian confirmation naming the period.
- The landlord sees pending payments in the admin, previews the receipt, and confirms (→ «оплачено») or rejects (→ back to «не оплачено»); deleting a receipt removes the file and reverts the statement.
- Delivery works both ways: `set_telegram_webhook <url>` for production (secret-checked) and `run_telegram_polling` for development.
- The `MessengerAdapter` seam is proven by the conforming (deferred) `MaxAdapter`.
- Full `pytest` suite is green.

## Deferred to Plan 2B

- Tenant **web receipt-upload** page (`«Загрузить чек»`) + `«Мои чеки»` list, reusing `attach_receipt`.
- Concrete **MaxAdapter** implementation against `platform-api.max.ru` (needs a verified legal entity to publish).

## Operator notes (for whoever runs it)

- Create the bot with **@BotFather**, put the token in `.env` as `TELEGRAM_BOT_TOKEN`, and set any long random `TELEGRAM_WEBHOOK_SECRET`.
- Dev: `python manage.py run_telegram_polling`. Prod (after deploy): `python manage.py set_telegram_webhook https://domiq-ufa.ru/bot/telegram/webhook/`.
- Follow-up to consider in 2B: receipt files under `/media` are currently reachable by anyone with the URL — add per-tenant access control when the tenant-facing «Мои чеки» view is built.
