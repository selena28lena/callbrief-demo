"""Встроенная демо-CRM: работает без интернета, чтобы показывать автоматизацию всегда."""

from .. import db, store
from .base import CrmAdapter

KEY = "demo_crm_log"


class DemoAdapter(CrmAdapter):
    name = "demo"
    title = "Демо-CRM (внутри CallBrief)"

    @property
    def connected(self) -> bool:
        return True

    def _log(self, entry: dict) -> str:
        items = store.setting(KEY, [])
        entry["id"] = str(len(items) + 1)
        items.insert(0, entry)
        store.set_setting(KEY, items[:200])
        return entry["id"]

    def list_deals(self, query: str = "", limit: int = 50) -> list[dict]:
        rows = db.query("SELECT id, company, name, stage FROM clients ORDER BY id LIMIT ?", (limit,))
        return [{"id": str(r["id"]), "title": r["company"] or r["name"], "stage": r["stage"] or "Новая"} for r in rows]

    def get_deal(self, deal_id: str) -> dict | None:
        row = store.client(int(deal_id)) if str(deal_id).isdigit() else None
        if not row:
            return None
        return {"id": str(row["id"]), "title": row["company"] or row["name"], "stage": row["stage"],
                "contact": {"name": row["name"], "phone": row["phone"], "post": ""}}

    def add_comment(self, deal_id: str, text: str) -> str:
        return self._log({"type": "comment", "deal_id": deal_id, "text": text})

    def create_task(self, deal_id: str, title: str, description: str = "", deadline: str | None = None) -> str:
        return self._log({"type": "task", "deal_id": deal_id, "title": title,
                          "description": description, "deadline": deadline})

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        self._log({"type": "deal_update", "deal_id": deal_id, "fields": fields})
        return True

    def journal(self) -> list[dict]:
        return store.setting(KEY, [])
