"""Общий интерфейс CRM. Приложение работает только через него."""

import os

from ..gemini import AppError


class CrmError(AppError):
    def __init__(self, message: str, status: int = 502):
        super().__init__("crm_error", message, status)


class CrmAdapter:
    """Минимальный набор операций, который нужен CallBrief от любой CRM."""

    name = "base"
    title = "CRM"

    @property
    def connected(self) -> bool:
        return False

    def status(self) -> dict:
        return {"provider": self.name, "title": self.title, "connected": self.connected}

    def list_deals(self, query: str = "", limit: int = 50) -> list[dict]:
        raise NotImplementedError

    def get_deal(self, deal_id: str) -> dict | None:
        raise NotImplementedError

    def add_comment(self, deal_id: str, text: str) -> str:
        raise NotImplementedError

    def create_task(self, deal_id: str, title: str, description: str = "", deadline: str | None = None) -> str:
        raise NotImplementedError

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        raise NotImplementedError

    def recent_calls(self, limit: int = 20) -> list[dict]:
        return []


def get_adapter():
    """Выбирает адаптер: Битрикс, если задан вебхук, иначе встроенная демо-CRM."""
    from . import bitrix, demo

    if os.getenv("BITRIX_WEBHOOK_URL", "").strip():
        return bitrix.BitrixAdapter()
    return demo.DemoAdapter()
