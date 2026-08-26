"""Миграции модуля лежат в `infrastructure/`, а не в `<модуль>/migrations/`.

Миграция — это ORM, и правило 3.2 держит ORM только здесь. Адрес объявлен в
`MIGRATION_MODULES` (`config/settings.py`). Подробности — `modules/README.md`.
"""
