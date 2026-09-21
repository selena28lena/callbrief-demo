"""Битрикс24 через входящий вебхук."""

import os
from datetime import datetime, timedelta

import httpx

from .base import CrmAdapter, CrmError

TIMEOUT = 25


def _webhook() -> str:
    url = os.getenv("BITRIX_WEBHOOK_URL", "").strip()
    return url.rstrip("/") + "/" if url else ""


class BitrixAdapter(CrmAdapter):
    name = "bitrix24"
    title = "Битрикс24"

    @property
    def connected(self) -> bool:
        return bool(_webhook())

    def call(self, method: str, params: dict | None = None) -> dict:
        url = _webhook()
        if not url:
            raise CrmError("Не задан BITRIX_WEBHOOK_URL в файле .env.", 400)
        try:
            response = httpx.post(f"{url}{method}.json", json=params or {}, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise CrmError("Не удалось связаться с Битрикс24. Проверьте интернет и адрес вебхука.") from e
        data = response.json() if response.content else {}
        if response.status_code >= 400 or "error" in data:
            message = data.get("error_description") or data.get("error") or f"HTTP {response.status_code}"
            if "expired" in str(message).lower() or "NO_AUTH" in str(data.get("error", "")):
                raise CrmError("Битрикс24 отклонил запрос: проверьте права вебхука или срок демо-подписки.", 401)
            raise CrmError(f"Битрикс24: {message}")
        return data

    def status(self) -> dict:
        info = super().status()
        info["portal"] = _webhook().split("/rest/")[0].replace("https://", "") if _webhook() else ""
        if self.connected:
            try:
                profile = self.call("profile").get("result", {})
                info["user"] = f"{profile.get('NAME', '')} {profile.get('LAST_NAME', '')}".strip()
                info["ok"] = True
            except CrmError as e:
                info["ok"] = False
                info["error"] = e.message
        return info

    # --- Сделки ---

    def list_deals(self, query: str = "", limit: int = 50) -> list[dict]:
        params = {
            "select": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "CONTACT_ID", "ASSIGNED_BY_ID", "DATE_CREATE"],
            "order": {"DATE_CREATE": "DESC"},
        }
        if query:
            params["filter"] = {"%TITLE": query}
        rows = self.call("crm.deal.list", params).get("result", [])[:limit]
        return [{"id": str(r["ID"]), "title": r.get("TITLE", ""), "stage": r.get("STAGE_ID", ""),
                 "amount": r.get("OPPORTUNITY"), "created": r.get("DATE_CREATE")} for r in rows]

    def get_deal(self, deal_id: str) -> dict | None:
        result = self.call("crm.deal.get", {"id": deal_id}).get("result")
        if not result:
            return None
        deal = {"id": str(result["ID"]), "title": result.get("TITLE", ""), "stage": result.get("STAGE_ID", ""),
                "amount": result.get("OPPORTUNITY"), "contact_id": result.get("CONTACT_ID"),
                "assigned_by": result.get("ASSIGNED_BY_ID"), "comments": result.get("COMMENTS", "")}
        if deal["contact_id"]:
            contact = self.call("crm.contact.get", {"id": deal["contact_id"]}).get("result", {})
            phones = contact.get("PHONE") or []
            deal["contact"] = {
                "name": " ".join(filter(None, [contact.get("NAME"), contact.get("LAST_NAME")])).strip(),
                "phone": phones[0]["VALUE"] if phones else "",
                "post": contact.get("POST", ""),
            }
        return deal

    def add_comment(self, deal_id: str, text: str) -> str:
        """Пишет разбор в ленту и в поле «Комментарий» самой сделки.

        Закрепить запись ленты через REST нельзя, поэтому дублируем текст в карточку:
        менеджер видит его сразу наверху, не пролистывая историю.
        """
        result = self.call("crm.timeline.comment.add", {
            "fields": {"ENTITY_ID": int(deal_id), "ENTITY_TYPE": "deal", "COMMENT": text}
        })
        try:
            self.call("crm.deal.update", {"id": deal_id, "fields": {"COMMENTS": text}})
        except (CrmError, httpx.HTTPError):
            pass   # лента важнее: если поле недоступно, комментарий всё равно сохранён
        return str(result.get("result", ""))

    def create_task(self, deal_id: str, title: str, description: str = "", deadline: str | None = None) -> str:
        fields = {
            "TITLE": title[:250],
            "DESCRIPTION": description,
            "RESPONSIBLE_ID": self._current_user_id(),
            "UF_CRM_TASK": [f"D_{deal_id}"],
        }
        if deadline:
            fields["DEADLINE"] = deadline
        result = self.call("tasks.task.add", {"fields": fields})
        task = result.get("result", {}).get("task", {})
        return str(task.get("id", ""))

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        mapped = {}
        if "stage" in fields:
            mapped["STAGE_ID"] = fields["stage"]
        if "comment" in fields:
            mapped["COMMENTS"] = fields["comment"]
        if not mapped:
            return False
        return bool(self.call("crm.deal.update", {"id": deal_id, "fields": mapped}).get("result"))

    def recent_calls(self, limit: int = 20) -> list[dict]:
        rows = self.call("voximplant.statistic.get", {"SORT": "CALL_START_DATE", "ORDER": "DESC"}).get("result", [])
        out = []
        for row in rows[:limit]:
            out.append({
                "id": str(row.get("ID")),
                "phone": row.get("PHONE_NUMBER"),
                "started_at": row.get("CALL_START_DATE"),
                "duration": row.get("CALL_DURATION"),
                "record_url": row.get("CALL_RECORD_URL"),
                "deal_id": str(row.get("CRM_ENTITY_ID")) if row.get("CRM_ENTITY_TYPE") == "DEAL" else None,
            })
        return out

    def _current_user_id(self) -> int:
        profile = self.call("profile").get("result", {})
        return int(profile.get("ID", 1))


def deadline_to_iso(text: str | None) -> str | None:
    """Превращает «в четверг», «завтра», «до пятницы» в дату для задачи."""
    if not text:
        return None
    lowered = text.lower()
    now = datetime.now()
    weekdays = {"понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5, "воскресень": 6}
    if "сегодня" in lowered:
        target = now.replace(hour=18, minute=0)
    elif "завтра" in lowered:
        target = (now + timedelta(days=1)).replace(hour=12, minute=0)
    else:
        target = None
        for name, index in weekdays.items():
            if name in lowered:
                delta = (index - now.weekday()) % 7 or 7
                target = (now + timedelta(days=delta)).replace(hour=11, minute=0)
                break
        if target is None:
            target = (now + timedelta(days=2)).replace(hour=12, minute=0)
    return target.strftime("%Y-%m-%dT%H:%M:%S+03:00")
