# Domiq — As-Is Inventory (Фаза 0)

Все ссылки — файл:строка на момент аудита. Только факты, без оценок.

---

## 1. Django-приложения

`INSTALLED_APPS` (config/settings.py:35-52):

```
django.contrib.admin
django.contrib.auth
django.contrib.contenttypes
django.contrib.sessions
django.contrib.messages
django.contrib.staticfiles
django.contrib.sites
crispy_forms
crispy_tailwind
allauth
allauth.account
allauth.socialaccount
allauth.socialaccount.providers.yandex
allauth.socialaccount.providers.vk
billing
billing.esia_provider
```

Проектных Django-приложений — **два**: `billing` и `billing.esia_provider`.
Всё остальное — сторонние пакеты (Django contrib, allauth, crispy).

Каталоги внутри `billing/` (не отдельные Django-приложения, обычные Python-пакеты
без `apps.py`/`AppConfig`, кроме `esia_provider`):

| Каталог/файл | Реальная ответственность (по коду) |
|---|---|
| `billing/models.py` | Все модели предметной области одним модулем: квартиры, жильцы, тарифы, счётчики, показания, начисления, документы, платежи (billing/models.py:1-192) |
| `billing/views.py` | HTTP-обработчики для арендатора: страница текущего месяца (ввод показаний + генерация начисления), история, документы, файлы, экран OAuth-подключений, публичная политика конфиденциальности (billing/views.py:1-141) |
| `billing/admin.py` | Django-admin для арендодателя: CRUD квартир/тарифов/показаний, ручной пересчёт начислений, подтверждение/отклонение платежей, показ превью чека (billing/admin.py:1-130) |
| `billing/forms.py` | Динамическая форма ввода показаний (по одному DecimalField на счётчик квартиры) + форма согласия на обработку ПДн (billing/forms.py:1-30) |
| `billing/adapters.py` | allauth `SocialAccountAdapter`: запрещает саморегистрацию через OAuth и требует действующего 152-ФЗ согласия перед привязкой нового провайдера (billing/adapters.py:1-26) |
| `billing/webhooks.py` | HTTP-эндпоинт приёма Telegram-апдейтов (проверка секрета, парсинг JSON, делегирование в `services.bot`) (billing/webhooks.py:1-29) |
| `billing/consent.py` | Единственная константа — текущая версия политики конфиденциальности (billing/consent.py:1-4) |
| `billing/urls.py` | Маршруты арендаторского веб-интерфейса и Telegram-вебхука (billing/urls.py:1-16) |
| `billing/services/calculation.py` | Чистая функция расчёта начисления по тарифу и потреблению (без Django ORM) (billing/services/calculation.py:1-129) |
| `billing/services/statements.py` | Оркестрация расчёта: достаёт показания/тарифы/конфиг квартиры из ORM, вызывает calculation, сохраняет `MonthlyStatement` (billing/services/statements.py:1-83) |
| `billing/services/intake.py` | Приём чека платежа и переходы статуса начисления/платежа (unpaid→pending→paid/rejected) (billing/services/intake.py:1-50) |
| `billing/services/linking.py` | Генерация и погашение кода привязки мессенджер-чата к арендатору (billing/services/linking.py:1-25) |
| `billing/services/bot.py` | Разбор входящих сообщений мессенджер-бота (Telegram/MAX): команда `/start <код>`, приём фото чека, диспетчеризация в intake/linking (billing/services/bot.py:1-64) |
| `billing/messengers/base.py` | Абстрактный интерфейс адаптера мессенджера (`MessengerAdapter`) (billing/messengers/base.py:1-30) |
| `billing/messengers/telegram.py` | Реализация адаптера для Telegram Bot API (billing/messengers/telegram.py:1-50) |
| `billing/messengers/max.py` | Заглушка адаптера для MAX — все методы `raise NotImplementedError` (billing/messengers/max.py:1-24) |
| `billing/management/commands/run_telegram_polling.py` | management-команда: long-polling Telegram вместо вебхука (billing/management/commands/run_telegram_polling.py:1-38) |
| `billing/management/commands/set_telegram_webhook.py` | management-команда: регистрация Telegram webhook URL (billing/management/commands/set_telegram_webhook.py:1-17) |
| `billing/esia_provider/provider.py` | allauth `OAuth2Provider` для Госуслуг (ESIA): регистрация провайдера, извлечение uid (billing/esia_provider/provider.py:1-21) |
| `billing/esia_provider/views.py` | allauth `OAuth2Adapter` для ESIA: URL авторизации/токена, декодирование id_token БЕЗ проверки подписи (billing/esia_provider/views.py:1-43) |
| `billing/esia_provider/urls.py` | Маршруты OAuth2-логина/коллбэка для ESIA (billing/esia_provider/urls.py:1-5) |
| `billing/esia_provider/apps.py` | `AppConfig.ready()` регистрирует `ESIAProvider` в реестре allauth (billing/esia_provider/apps.py:1-11) |

---

## 2. Граф импортов

Проектных Python-пакетов, участвующих в импортах, — `billing` и `billing.esia_provider`.
Кросс-приложénных импортов между ними в рантайм-коде нет: `esia_provider` не импортирует
ничего из `billing`, а `billing` не импортирует ничего из `esia_provider` напрямую — связь
идёт только через реестр allauth (`billing/esia_provider/apps.py:8-10` регистрирует
провайдера, `config/urls.py:30-37` затем обходит реестр allauth, включая маршруты
зарегистрированных провайдеров, включая esia).

Импорты `billing.*` из management-команд (единственные потребители пакетов `services`/
`messengers` вне `billing/views.py`, `billing/admin.py`, `billing/webhooks.py`):

- `billing/management/commands/run_telegram_polling.py:5-6` — импортирует
  `billing.messengers.telegram.TelegramAdapter`, `billing.messengers.telegram.API`,
  `billing.services.bot.handle_update`.
- `billing/management/commands/set_telegram_webhook.py:2` — импортирует
  `billing.messengers.telegram.TelegramAdapter`.

Внутренние импорты внутри `billing` (по слоям, как они фактически устроены сейчас):

- `billing/views.py:10-14` импортирует из `billing.consent`, `billing.forms`,
  `billing.models` (`Document`, `MeterReading`, `MonthlyStatement`, `Tenant`),
  `billing.services.calculation` (`MissingTariffError`),
  `billing.services.statements` (`MissingBaselineError`, `meters_for`, `generate_statement`).
- `billing/admin.py:4-8` импортирует из `billing.models` (все модели),
  `billing.services.statements.generate_statement`,
  `billing.services.intake` (`confirm_payment`, `reject_payment`, `_revert_if_no_pending` —
  admin напрямую использует приватную функцию сервиса, обозначенную ведущим `_`).
- `billing/webhooks.py:7-8` импортирует `billing.messengers.telegram.TelegramAdapter`,
  `billing.services.bot.handle_update`.
- `billing/adapters.py:4` импортирует `billing.consent.PRIVACY_POLICY_VERSION`.
- `billing/services/statements.py:2-3` импортирует `billing.services.calculation`
  (`ApartmentConfig`, `MeterType`, `compute_statement`) и `billing.models`
  (`Apartment`, `Tariff`, `MeterReading`, `MonthlyStatement`).
- `billing/services/intake.py:2` импортирует `billing.models`
  (`MonthlyStatement`, `Payment`).
- `billing/services/linking.py:2` импортирует `billing.models.Tenant`.
- `billing/services/bot.py:6-8` импортирует `billing.models.Tenant`,
  `billing.services.intake` (`attach_receipt`, `NoUnpaidStatementError`),
  `billing.services.linking` (`link_chat`, `InvalidLinkCodeError`).
- `billing/services/calculation.py` — не импортирует ничего из `billing` (единственный
  модуль без зависимости на Django ORM/модели, см. §4).
- `billing/esia_provider/provider.py:3` импортирует `billing.esia_provider.views.ESIAOAuth2Adapter`
  (внутри своего же подпакета, не пересекает границу `billing`/`esia_provider`).
- `billing/esia_provider/apps.py:9` импортирует `billing.esia_provider.provider.ESIAProvider`
  (тот же подпакет).

Сторонние (не проектные) импорты, определяющие фактические зависимости:
`django.conf.settings`, `django.db.models`, `allauth.socialaccount.models.SocialAccount`
(billing/views.py:9), `allauth.core.exceptions.ImmediateHttpResponse`,
`allauth.socialaccount.adapter.DefaultSocialAccountAdapter` (billing/adapters.py:1-2),
`allauth.socialaccount.providers.*` (esia_provider/*).

---

## 3. ForeignKey / OneToOne / M2M

Все модели определены в одном файле `billing/models.py`, поэтому все связи —
внутри одного Django-приложения. Таблица перечисляет их с указанием на какую
модель (и, для справки, к какому будущему домену по брифу she относится) указывает
каждое поле:

| Модель | Поле | on_delete | Куда указывает | Строка |
|---|---|---|---|---|
| `Tenant` | `user` (OneToOne) | CASCADE | `settings.AUTH_USER_MODEL` (django.contrib.auth.User) | billing/models.py:38-39 |
| `Tenant` | `apartment` (FK) | PROTECT | `Apartment` | billing/models.py:40 |
| `Meter` | `apartment` (FK) | PROTECT ¹ | `Apartment` | billing/models.py:99 |
| `MeterReading` | `apartment` (FK) | PROTECT ¹ | `Apartment` | billing/models.py:116 |
| `MonthlyStatement` | `apartment` (FK) | PROTECT ¹ | `Apartment` | billing/models.py:135 |
| `Document` | `tenant` (FK) | CASCADE | `Tenant` | billing/models.py:154 |
| `Payment` | `statement` (FK) | CASCADE | `MonthlyStatement` | billing/models.py:177-178 |

¹ На момент снятия слепка здесь стоял `CASCADE` — это и есть дефект №9
гап-анализа: удаление квартиры уносило приборы, показания и все счета. Три
поля переведены на `PROTECT` миграцией
[`0007_apartment_deletion_is_protected`](../../billing/migrations/0007_apartment_deletion_is_protected.py)
до начала этапа B. Остальные строки таблицы — как были.

Замечания по факту хранения данных (без оценки):
- `MeterReading.meter` и `Meter.kind` — не FK, а `CharField` с общими `choices`
  из `METER_KIND_CHOICES` (billing/models.py:88-94), используемым в обеих моделях
  (billing/models.py:100, 118).
- `Tariff.utility_type` — независимый `CharField` с собственным `UTILITY_CHOICES`
  (billing/models.py:61-72), коды частично, но не полностью совпадают с
  `METER_KIND_CHOICES` (у `Tariff` есть `hot_water_cold_component` /
  `hot_water_heat_component`, которых нет в `METER_KIND_CHOICES`).
- M2M-полей в проекте нет.
- Аутентификационные данные жильца (User) и профиль жильца (Tenant) — раздельные
  модели, связанные `OneToOneField` (billing/models.py:38-39); `SocialAccount`
  (allauth) связан с тем же `User`, но не с `Tenant`.

---

## 4. Три сценария: путь кода

### 4.1 Расчёт начисления

Точки входа (все вызывают одну и ту же функцию `generate_statement`):
1. `billing/views.py:63` — внутри `current_month` (POST), после сохранения показаний
   в транзакции (billing/views.py:51-63).
2. `billing/admin.py:46` — `MeterReadingAdmin.save_model`, после сохранения показания
   через admin-форму (billing/admin.py:43-52).
3. `billing/admin.py:59` — admin-action `regenerate_statements` над выборкой
   `MonthlyStatement` (billing/admin.py:54-68).

Бизнес-логика (оркестрация): `billing/services/statements.py:65-82`
(`generate_statement`):
- собирает `ApartmentConfig` из полей модели `Apartment`
  (billing/services/statements.py:66-73);
- читает текущие показания (`_readings_map`, billing/services/statements.py:20-22)
  и базовые/предыдущие показания (`_previous_readings`,
  billing/services/statements.py:24-44 — либо последняя `MeterReading` до периода,
  либо `Meter.initial_value`, иначе `MissingBaselineError`);
- читает действующие тарифы на период (`_tariffs_for`,
  billing/services/statements.py:46-54 — последний `Tariff` с
  `effective_from <= period` для каждого `utility_type`);
- передаёт всё в чистую функцию расчёта.

Собственно расчёт (доменная логика без Django/ORM):
`billing/services/calculation.py:78-128` (`compute_statement`) — считает построчно
холодную/горячую воду (двухкомпонентный ГВС, billing/services/calculation.py:85-101),
водоотведение (строки 102-105), электричество (однотарифное или день/ночь,
строки 107-113), фиксированные платежи (аренда/интернет/прочее, строки 115-118),
итог с опциональным округлением вниз до 50 ₽ при превышении 10 000 ₽
(строки 120-127). Проверка "показание не может уменьшаться" — в
`_consumption` (billing/services/calculation.py:59-65), вызывается из
`_metered_line` (строки 73-76) и напрямую для горячей воды (строка 89).

Сохранение: `MonthlyStatement.objects.update_or_create(...)` по ключу
`(apartment, period)` (billing/services/statements.py:78-81), пишет поля
`lines` (JSONField сериализованных `LineItem`, billing/services/statements.py:56-63)
и `total`.

### 4.2 Фиксация показания счётчика

Точка входа: `billing/views.py:current_month`, POST-ветка
(billing/views.py:42-81). Форма `MeterReadingForm` строится динамически по
списку счётчиков квартиры (`meters_for`, billing/services/statements.py:8-18,
вызывается в billing/views.py:36) и текущим серийным номерам
(billing/views.py:37).

Блокировка: если у квартиры уже есть `MonthlyStatement` за период со статусом
`paid` или `pending`, форма не принимает POST — редирект с сообщением об ошибке
(billing/views.py:40, 43-45); проверка выполняется до валидации формы.

Бизнес-логика/запись — прямо во view, без отдельного сервиса:
для каждого счётчика квартиры (`meters`, billing/views.py:52) находится
существующая запись `MeterReading` за период (billing/views.py:48-49) —
если есть, обновляется `value` и `entered_by_tenant=True` и сохраняется
(billing/views.py:55-58); если нет — создаётся новая
(billing/views.py:59-62). Всё — в `transaction.atomic()`
(billing/views.py:51). Сразу после — вызывается `generate_statement`
(billing/views.py:63, см. §4.1); ошибка уменьшения показания
(`ValueError` из `_consumption`, calculation.py:64) перехватывается тут же
(billing/views.py:64-68).

Альтернативный путь фиксации показания — Django admin,
`MeterReadingAdmin` (billing/admin.py:37-52): прямое CRUD-редактирование модели
`MeterReading` через стандартную admin-форму, `save_model` переопределён только
для последующего вызова `generate_statement` (billing/admin.py:43-52).

### 4.3 Определение статуса оплаты

Хранение статуса — два независимых поля-перечисления на двух моделях:
`MonthlyStatement.status` (`unpaid`/`pending`/`paid`, billing/models.py:132-139)
и `Payment.status` (`pending`/`confirmed`/`rejected`, billing/models.py:172-181).
Прямой связи между значениями через код (enum) нет — переходы обеих моделей
координируются функциями `billing/services/intake.py`.

Точки входа, создающие/меняющие статус:
1. Приём чека через Telegram-бот: `billing/webhooks.py:26`
   (`telegram_webhook` → `handle_update`) → `billing/services/bot.py:57-63`
   (`handle_update`) → `billing/services/bot.py:26-54` (`process_message`,
   ветка с `msg.file_id`, строки 40-49) → `billing/services/bot.py:46`
   вызывает `attach_receipt`.
2. Приём чека через long-polling: `billing/management/commands/run_telegram_polling.py:15`
   → тот же `handle_update`.
3. Подтверждение/отклонение платежа арендодателем — только через Django admin:
   admin-actions `confirm_payments` (billing/admin.py:70-75, вызывает
   `confirm_payment` для каждого `Payment` со статусом `pending`) и
   `reject_payments` (billing/admin.py:77-82, вызывает `reject_payment`).
   Отдельный API/веб-роут для арендодателя отсутствует — только admin.

Примечание по факту: `Payment.SOURCE_CHOICES` включает значение `web`
(billing/models.py:170-171, `WEB = "web"`), но в `billing/urls.py` и
`billing/views.py` нет обработчика, создающего `Payment` с `source="web"` —
единственный вызывающий код `attach_receipt` с явным `source` — это
`billing/services/bot.py:46`, где `source=msg.platform` (`"telegram"` либо `"max"`).

Бизнес-логика перехода статусов — `billing/services/intake.py`:
- `attach_receipt` (строки 12-21): требует наличие `MonthlyStatement` со
  статусом `unpaid` (`earliest_unpaid_statement`, строки 7-10 — иначе
  `NoUnpaidStatementError`), создаёт `Payment` с `status="pending"` (default,
  billing/models.py:181), переводит связанный `MonthlyStatement.status` в
  `pending` (строки 19-21).
- `confirm_payment` (строки 24-30): `Payment.status = "confirmed"`,
  затем `MonthlyStatement.status = "paid"`.
- `reject_payment` (строки 41-49): `Payment.status = "rejected"`,
  затем `_revert_if_no_pending` (строки 32-39) — возвращает
  `MonthlyStatement.status` в `unpaid`, только если статус ещё не `paid`
  и не осталось других `Payment` со статусом `pending` (проверка через
  `stmt.payments.filter(status=Payment.PENDING).exists()`, строка 37).
- Та же `_revert_if_no_pending` вызывается также из admin при удалении
  платежа с диска (`PaymentAdmin._delete_with_file`,
  billing/admin.py:102-106) — admin импортирует и использует эту функцию
  напрямую, хотя имя начинается с `_` (billing/admin.py:8, 106).

---

## 5. Неявные связи

- **Django signals**: не найдено ни одного (`grep -rn "signal\|receiver\|post_save\|pre_save\|post_delete"` по `billing/` и `config/` — 0 совпадений).
- **Celery**: в проекте не подключён (нет `celery`/`shared_task` в коде;
  доставка мессенджер-апдейтов реализована через HTTP-вебхук
  (billing/webhooks.py) или через management-команду long-polling
  (billing/management/commands/run_telegram_polling.py), а не через
  фоновую очередь задач).
- **Raw SQL / JOIN между таблицами разных доменов**: не найдено (`grep -rn
  "\.raw(\|RawSQL\|cursor()"` — 0 совпадений). Все запросы — стандартный
  Django ORM, все таблицы принадлежат одному приложению `billing`.
- **Общая функция для двух future-модулей**: `billing/admin.py:8` напрямую
  импортирует приватную функцию `_revert_if_no_pending` из
  `billing/services/intake.py` (обычно приватные `_`-имена не пересекают
  границу модуля — здесь пересекают границу файла admin.py/services/intake.py
  внутри одного приложения).
- **Общий словарь кодов счётчика между моделями**: `METER_KIND_CHOICES`
  (billing/models.py:88-94) — единый источник строковых кодов, используемый
  и в `Meter.kind` (billing/models.py:100), и в `MeterReading.meter`
  (billing/models.py:118), и (по значению строк, без общего импорта) в
  `LABELS` и ветвлениях `billing/services/calculation.py:45-56, 82-113`, и
  в `billing/services/statements.py:9-17` (`meters_for`, генерирует те же
  строковые коды по условию из `Apartment`, не импортируя `METER_KIND_CHOICES`).
- **Косвенная связь через allauth-реестр**: `billing/esia_provider/apps.py:6-10`
  регистрирует `ESIAProvider` в `allauth.socialaccount.providers.registry`
  при старте приложения; `config/urls.py:30-37` (`_provider_urlpatterns`)
  на старте обходит тот же реестр, чтобы подключить маршруты — связь между
  `billing.esia_provider` и `config` идёт не через прямой импорт, а через
  общий процесс-глобальный реестр allauth.
- **`SocialAccount` (allauth) как неявная связь с `Tenant`**: `billing/views.py:9,
  134-135` читает `allauth.socialaccount.models.SocialAccount` по
  `request.user`, но нет FK между `SocialAccount`/`Tenant` — связь только
  через общий `User`.

---

## 6. Ключевые факты для нарезки модулей

1. Весь код предметной области сейчас живёт в одном Django-приложении
   `billing/models.py` — модели будущих Identity, Tenancy, Properties,
   Metering, Tariffs, Billing, Payments сегодня физически неразличимы:
   `Apartment`, `Tenant`, `Tariff`, `Meter`, `MeterReading`,
   `MonthlyStatement`, `Document`, `Payment` — один файл, одна таблица
   на модель, без префиксов.
2. Статус оплаты хранится в **двух местах одновременно** и координируется
   вручную: `MonthlyStatement.status` (billing/models.py:139) и
   `Payment.status` (billing/models.py:181), синхронизация — императивным
   кодом в `billing/services/intake.py:12-49`, а не единым источником
   истины.
3. Фиксация показания счётчика — бизнес-логика (валидация, upsert,
   транзакция) находится прямо в HTTP-view (`billing/views.py:42-81`),
   а не в сервисном слое; сервисный слой (`services/statements.py`,
   `services/calculation.py`) вызывается уже post-factum, для генерации
   начисления.
4. Расчёт начисления (`compute_statement`,
   billing/services/calculation.py:78-128) — единственный полностью чистый
   модуль без импорта Django ORM/моделей во всём проекте; всё остальное
   (`statements.py`, `intake.py`, `linking.py`, `views.py`, `admin.py`)
   обращается к `billing.models` напрямую.
5. Тарифы (`Tariff`) и Начисления (`MonthlyStatement`) читаются/пишутся
   из одного и того же сервисного модуля `services/statements.py`, без
   разделения на отдельный публичный API — `_tariffs_for`
   (billing/services/statements.py:46-54) обращается к `Tariff.objects`
   напрямую внутри функции, которая также создаёт `MonthlyStatement`.
6. Admin-слой (`billing/admin.py`) обходит сервисный слой там, где ему
   удобно: вызывает публичные сервисные функции (`generate_statement`,
   `confirm_payment`, `reject_payment`), но также напрямую вызывает
   приватную `_revert_if_no_pending` (billing/admin.py:8, 106) и
   выполняет собственную бизнес-операцию (`PaymentAdmin._delete_with_file`,
   billing/admin.py:102-106: удаление файла + запись + пересчёт статуса)
   вне сервисного модуля `intake.py`.
7. Единственный второй Django-app в проекте, `billing.esia_provider`,
   уже сейчас изолирован от `billing` (нет прямых импортов в обе стороны,
   billing/esia_provider/*.py) — связь идёт исключительно через allauth
   provider registry (billing/esia_provider/apps.py:6-10,
   config/urls.py:30-37), что на практике уже является примером
   границы, спроектированной без общих моделей/ORM-связей.
