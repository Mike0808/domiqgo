# Utility Billing Portal for Renters — Design Spec

**Date:** 2026-07-23
**Location context:** Ufa, Republic of Bashkortostan, Russia
**Status:** Approved design, ready for implementation planning

---

## 1. Purpose

A web application for a **single landlord** managing **many rental units** to bill tenants
for public utilities (ЖКХ) and rent. Tenants log in to a mobile-first portal to submit
their own meter readings, see their monthly consumption and bill breakdown, prove payment
by uploading a receipt (via a messenger bot or the web), and access their rental agreement.

The landlord runs the whole operation from the Django admin: creating tenant cards,
setting initial meter readings, managing time-versioned tariffs, and approving payments.

### Users
- **Landlord (you)** — a single Django superuser/staff account. Full back-office control.
- **Tenant (жилец)** — a Django `User` linked to one apartment; login + password issued by
  the landlord. Sees and edits only their own data.

---

## 2. Scope

### In scope
- Web portal for tenants (readings, bill, history, receipts, documents).
- Django admin back-office for the landlord.
- Calculation core for utilities with time-versioned tariffs.
- Receipt intake via **web upload** and a **messenger bot** (Telegram + MAX), sharing one code path.
- Payment approval workflow: `не оплачено → на проверке → оплачено`.
- Rental agreement (and other documents) attached to a tenant.
- Tariff source links (provenance).

### Out of scope (for now — YAGNI)
- Multiple landlords / SaaS multi-tenancy.
- Meter-reading submission via the bot (bot handles receipts only for now).
- Automated payment verification (no OCR/parsing of receipts; confirmation is manual).
- Online payment collection (the app records proof of payment, it does not process payments).
- SMS/email login.

---

## 3. Language & localization

- Tenant UI and admin in **Russian**. `LANGUAGE_CODE = 'ru'`, `TIME_ZONE = 'Asia/Yekaterinburg'`
  (Ufa is UTC+5). Currency displayed as **₽**, dates in Russian format.

---

## 4. Domain model

Fields listed are the meaningful ones; standard `id`, `created_at`, `updated_at` are implied.

### Apartment (Квартира)
- `label` — address / short name.
- `electricity_meter_type` — `single` | `dual` (день/ночь). Configurable per apartment.
- Applicable utilities flags (which meters this apartment has).
- Fixed monthly charges: `rent`, `internet`, `other_fixed` (each an amount in ₽).
- `active_tenant` — FK to the currently assigned Tenant (nullable).

### Tenant (Жилец)
- `user` — One-to-one with Django `User` (login + password).
- `apartment` — FK to Apartment.
- `messenger_platform` — `telegram` | `max` | null.
- `messenger_chat_id` — set after the tenant links their chat.
- `link_code` — one-time code the landlord gives the tenant to link the bot.
- Tenant turnover: create a new Tenant card + new baseline readings; historical data is preserved.

### Tariff (Тариф)
- `utility_type` — one of `cold_water`, `hot_water`, `sewage`,
  `electricity_single`, `electricity_day`, `electricity_night`.
- `rate` — ₽ per unit (m³ or kWh).
- `effective_from` — date the rate takes effect. **Time-versioned**: the app selects the
  tariff in effect for each billing period, so historical months keep their old rates.
- `source_name`, `source_url` — official page the rate is based on (provenance). Each
  historical rate keeps its own source link.

### MeterReading (Показание)
- `apartment` — FK.
- `period` — billing month (year-month).
- `meter` — which meter: `cold_water`, `hot_water`, `electricity_single`,
  `electricity_day`, `electricity_night`.
- `value` — the reading.
- The **initial** readings the landlord enters when creating the card are simply the first
  records for that apartment; each subsequent month the tenant adds new ones.

### MonthlyStatement (Начисление)
- `apartment` — FK.
- `period` — billing month.
- Computed line items (per utility + fixed lines) and `total`.
- `status` — `unpaid` (не оплачено) | `pending` (на проверке) | `paid` (оплачено).
- One statement per apartment per period. Editable until confirmed paid.

### Payment (Платёж)
- `statement` — FK to MonthlyStatement.
- `image` / `file` — the receipt (image or PDF).
- `source` — `telegram` | `max` | `web`.
- `submitted_at`.
- `status` — `pending` → `confirmed`. Confirming flips the statement to `paid`.

### Document (Документ)
- `tenant` (or `apartment`) — FK.
- `file` — PDF or image.
- `title` — default «Договор аренды».
- `uploaded_at`.
- Modeled as a list so a card can hold the agreement plus extras later
  (акт приёма-передачи, опись имущества) with no schema change.

---

## 5. Calculation core (isolated, test-first)

A **pure function** is the heart of the app and is built test-first:

```
compute_statement(apartment_config, current_readings, previous_readings,
                  tariffs_for_period, fixed_charges) -> line_items, total
```

Logic:
- **Cold water:** `(current − previous) m³ × cold_water tariff`
- **Hot water:** `(current − previous) m³ × hot_water tariff`
- **Sewage (водоотведение):** `(cold consumption + hot consumption) × sewage tariff`
- **Electricity — single:** `(current − previous) kWh × electricity_single tariff`
- **Electricity — dual:** day and night computed separately with their own tariffs, then summed
- **Fixed lines:** `rent + internet + other_fixed`, added as-is
- **Total:** sum of all line items

Tariff selection: for a given `period`, use the tariff of each `utility_type` whose
`effective_from` is the latest date `<= period start`.

This function has no I/O and no framework dependencies, so it is unit-tested exhaustively,
including edge cases (dual vs single, missing tariff, zero consumption).

---

## 6. Tenant portal (mobile-first, Russian)

- **Login** — username + password issued by the landlord.
- **Это месяц (current month):**
  - Form to enter current meter readings for this apartment's meters.
  - After submission, shows the bill breakdown (each line + tariff + source link) and total.
  - **«Загрузить чек»** — upload a receipt (image/PDF) directly in the browser.
  - Payment status badge: не оплачено / на проверке / оплачено.
- **История (history):** past months — consumption per utility and amount, status, with a
  simple by-month consumption view.
- **Мои чеки:** list of submitted receipts (period, submit date, status), openable/downloadable.
- **Мои документы:** the rental agreement (and any extra documents) to open/download.
- A tenant can only ever see and edit **their own** apartment/data.

---

## 7. Receipt intake (shared code path)

Both the **web upload** and the **bot** call the same intake service:
1. Create a `Payment`, attach the file.
2. Attach it to the tenant's **earliest unpaid** `MonthlyStatement`.
3. Set that statement to **`pending` (на проверке)**.
4. Notify the landlord.

`Payment.source` records where it came from (`telegram` / `max` / `web`). Identical
validation and status behavior regardless of channel. The **web upload is the
always-available path**; the bot is the convenience path.

Edge cases: no unpaid statement → polite "нет неоплаченных начислений"; unsupported file
type / oversize → rejected with a clear message.

---

## 8. Messenger bot (Telegram + MAX)

### Abstraction — the key to supporting both
A single `MessengerAdapter` interface: `parse_update`, `download_file`, `send_message`,
`set_webhook`. Two implementations: `TelegramAdapter`, `MaxAdapter`. All app logic talks to
the interface, never a specific platform. A config setting selects the live adapter. Webhook
in production, long-polling in development. Adding/switching a platform touches only its adapter.

### Platform notes
- **Telegram** — no legal-entity requirement; works for an individual; mature API. Default/fallback.
- **MAX** (VK, 2025) — real Bot API at `platform-api.max.ru`, official Python library, 30 req/s,
  webhook + long-polling. **Publishing a bot requires a verified Russian legal entity (ИП/юрлицо)
  since Aug 2025.** Usable once the landlord registers an entity.

### Linking a tenant
On tenant-card creation the app generates a one-time `link_code`. The landlord gives it to the
tenant; the tenant sends `/start <code>` to the bot; the bot stores `chat_id` + platform on the
Tenant. Thereafter the bot recognizes them automatically.

### Receipt flow via bot
Linked tenant sends a photo → bot downloads it → shared intake service (section 7) →
bot replies confirming the period («Чек получен, начисление за <период> отправлено на проверку»).

### Edge cases
Unknown/unlinked chat → bot asks for the link code; non-image message → hint to send a photo;
download failure → retry/notify; webhook secured with a secret token; image size limit.

---

## 9. Admin back-office (landlord)

Built on Django admin, shaped into a real workflow rather than bare CRUD.

- **Pending-payments queue** — filtered view of everything `pending`. Each row shows tenant,
  period, amount, and a **preview of the receipt**. Action **«Подтвердить оплату»** →
  `paid`; reject → back to `unpaid` with an optional note. Bulk-approve supported.
- **Delete / replace attached files** — remove a wrong receipt or superseded agreement scan;
  deleting a confirmed receipt reverts the statement status cleanly.
- **Everything editable** — apartments, tenants (incl. reissuing a bot link code or resetting a
  password), tariffs + source links, meter readings (with an admin **override** for legitimate
  meter swaps where a new reading is lower), statements.
- Changes logged via Django's built-in admin history.

---

## 10. Validation & error handling

- A new meter reading must be **≥ the previous** reading; a lower value is blocked, with an
  admin override for genuine meter replacements.
- One reading set per apartment per month; editable until the statement is marked paid.
- **Missing tariff** for a period surfaces a clear error to the landlord — never a silent wrong bill.
- Access control: a tenant can only reach their own apartment, readings, statements, receipts,
  and documents.
- File uploads: allowed types (common images + PDF), size limit, stored in media storage.

---

## 11. Tech & hosting

- **Django 5 / Python 3.12+**, server-rendered templates (no separate frontend build).
- **Dev:** SQLite on the landlord's Windows PC; bot via long-polling.
- **Prod:** PostgreSQL on a Russian VPS (Timeweb Cloud or Selectel, ~200–400 ₽/mo),
  Ubuntu + gunicorn + nginx, WhiteNoise (or nginx) for static files, webhook for the bot.
  Designed to run identically local and on the VPS.
- **Auth:** Django's built-in auth. Landlord = superuser/staff; tenant = `User` + Tenant profile.
- **Media:** uploaded receipts and documents in media storage with access control.
- **Tests:** Django test suite, concentrated on the calculation core and the receipt-intake service.

---

## 12. Statuses summary

- **Meter readings:** entered by landlord (initial) then by tenant (monthly).
- **Payment lifecycle:** `не оплачено (unpaid) → на проверке (pending) → оплачено (paid)`,
  with an admin reject path back to `unpaid`.
