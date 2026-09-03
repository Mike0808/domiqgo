"""Транспортные адаптеры — инфраструктура Notifications (шаг F2).

Интерфейсный слой (бот, вебхук, management-команды) пользуется теми же
адаптерами для диалога — в домен модуля при этом не заходя (спецификация,
«Не входит»).
"""

from .base import IncomingMessage, MessengerAdapter


def transport_for(platform: str):
    """Адаптер по имени платформы — для прогона отправки."""
    from .email import EmailTransport
    from .max import MaxAdapter
    from .telegram import TelegramAdapter

    adapters = {"telegram": TelegramAdapter, "max": MaxAdapter,
                "email": EmailTransport}
    return adapters[platform]()
