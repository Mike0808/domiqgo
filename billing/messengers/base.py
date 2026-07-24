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
