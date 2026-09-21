"""CRM: статус подключения, привязка сделок и применение действий одной кнопкой."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db, store
from ..crm import base as crm_base
from ..crm.bitrix import deadline_to_iso
from ..gemini import AppError
from ..session import current_user

router = APIRouter(prefix="/api/crm", tags=["crm"])


class PlacementPayload(BaseModel):
    url: str


class LinkPayload(BaseModel):
    call_id: int
    deal_id: str
    deal_title: str | None = None


def adapter():
    return crm_base.get_adapter()


@router.get("/status")
def status(user: dict = Depends(current_user)):
    return adapter().status()


@router.get("/deals")
def deals(q: str = "", user: dict = Depends(current_user)):
    return {"items": adapter().list_deals(query=q, limit=50)}


@router.get("/calls")
def crm_calls(user: dict = Depends(current_user)):
    """Последние звонки из телефонии CRM — источник записей для анализа."""
    return {"items": adapter().recent_calls(limit=20)}


@router.post("/link")
def link_deal(body: LinkPayload, user: dict = Depends(current_user)):
    call = store.call(body.call_id)
    if not call:
        raise AppError("not_found", "Звонок не найден.", 404)
    client_id = call["client_id"]
    if not client_id:
        client_id = store.find_or_create_client(body.deal_title or f"Сделка {body.deal_id}", owner_id=user["id"])
        store.update_call(body.call_id, client_id=client_id)
    db.execute("UPDATE clients SET crm_id = ?, crm_kind = 'deal' WHERE id = ?", (body.deal_id, client_id))
    return {"ok": True, "client_id": client_id}


def _deal_id_for(call: dict, deal_id: str | None = None) -> str:
    """Сделка берётся из самого звонка: он помнит карточку, из которой его загрузили."""
    if deal_id:
        return str(deal_id)
    if call.get("crm_deal_id"):
        return str(call["crm_deal_id"])
    client = store.client(call["client_id"]) if call["client_id"] else None
    if client and client.get("crm_id"):
        return client["crm_id"]
    # Во встроенной демо-CRM сделка — это карточка клиента, её можно определить без выбора
    if client and adapter().name == "demo":
        return str(client["id"])
    raise AppError("no_deal", "Звонок не связан со сделкой в CRM. Выберите сделку и повторите.", 400)


def apply_one(action: dict, call: dict, deal_id: str, crm) -> dict:
    """Отправляет одно действие в CRM и помечает его применённым."""
    payload = action["payload"]
    kind = action["type"]
    external_id = ""
    try:
        if kind == "crm_comment":
            external_id = crm.add_comment(deal_id, payload.get("text", ""))
        elif kind == "task":
            owner_bit = f" Ответственный: {payload['owner']}." if payload.get("owner") else ""
            external_id = crm.create_task(
                deal_id,
                payload.get("title") or "Задача по итогам звонка",
                (payload.get("description") or f"Поставлено CallBrief по звонку «{call['title']}».") + owner_bit,
                deadline_to_iso(payload.get("deadline")),
            )
        elif kind == "next_contact":
            external_id = crm.create_task(
                deal_id,
                f"Связаться с клиентом ({payload.get('when', 'скоро')})",
                "Следующий контакт по итогам разговора. Поставлено CallBrief.",
                deadline_to_iso(payload.get("when")),
            )
        elif kind in ("tags", "deal_update"):
            # Раньше теги затирали поле «Комментарий» сделки — теперь итог входит в сам комментарий
            store.update_action(action["id"], status="skipped")
            return {"id": action["id"], "type": kind, "status": "skipped"}
        elif kind == "follow_up":
            external_id = crm.add_comment(deal_id, "Письмо клиенту:\n" + payload.get("text", ""))
        store.update_action(action["id"], status="applied", external_id=str(external_id),
                            applied_at=db.query("SELECT datetime('now') AS t")[0]["t"])
        return {"id": action["id"], "type": kind, "status": "applied", "external_id": str(external_id)}
    except AppError as e:
        store.update_action(action["id"], status="failed", error=e.message)
        return {"id": action["id"], "type": kind, "status": "failed", "error": e.message}


@router.post("/apply/{action_id}")
def apply_action(action_id: int, deal_id: str | None = None, user: dict = Depends(current_user)):
    action = store.action(action_id)
    if not action:
        raise AppError("not_found", "Действие не найдено.", 404)
    call = store.call(action["call_id"])
    return apply_one(action, call, _deal_id_for(call, deal_id), adapter())


@router.post("/apply-call/{call_id}")
def apply_call(call_id: int, deal_id: str | None = None, user: dict = Depends(current_user)):
    """«Сохранить всё»: комментарий, задача и следующий контакт уходят в CRM одной кнопкой.

    deal_id передаёт панель из карточки сделки — так запись гарантированно уходит в ту карточку,
    которая открыта у менеджера, даже если один и тот же звонок загружали в разные сделки.
    """
    call = store.call(call_id)
    if not call:
        raise AppError("not_found", "Звонок не найден.", 404)
    target = _deal_id_for(call, deal_id)
    if target != (call.get("crm_deal_id") or ""):
        store.update_call(call_id, crm_deal_id=target)
    crm = adapter()
    results = [apply_one(a, call, target, crm) for a in store.actions(call_id=call_id, status="draft")]
    store.update_call(call_id, status="saved")
    return {"results": results, "applied": sum(1 for r in results if r["status"] == "applied"),
            "deal_id": target, "provider": crm.title}


@router.get("/journal")
def journal(user: dict = Depends(current_user)):
    """Журнал демо-CRM: что бы ушло в настоящую систему."""
    crm = adapter()
    return {"items": crm.journal() if hasattr(crm, "journal") else [], "provider": crm.title}


PLACEMENTS = [
    ("CRM_DEAL_DETAIL_TOOLBAR", "CallBrief — разбор звонка"),
    ("CRM_DEAL_DETAIL_TAB", "CallBrief"),
]


@router.post("/placement/bind")
def bind_placement(body: PlacementPayload, user: dict = Depends(current_user)):
    """Добавляет кнопку CallBrief в карточку сделки Битрикс24."""
    crm = adapter()
    if crm.name != "bitrix24":
        raise AppError("crm_error", "Кнопка в карточке доступна только для Битрикс24.", 400)
    handler = body.url.rstrip("/") + "/embed"
    bound = []
    for code, title in PLACEMENTS:
        try:
            crm.call("placement.unbind", {"PLACEMENT": code})
        except AppError:
            pass
        crm.call("placement.bind", {
            "PLACEMENT": code,
            "HANDLER": handler,
            "TITLE": title,
            "DESCRIPTION": "AI-разбор звонка: комментарий и задача в один клик",
        })
        bound.append(code)
    store.set_setting("embed_url", handler)
    return {"ok": True, "handler": handler, "placements": bound}


@router.get("/placement")
def placement_status(user: dict = Depends(current_user)):
    crm = adapter()
    if crm.name != "bitrix24":
        return {"supported": False, "items": []}
    try:
        items = crm.call("placement.list").get("result", [])
        return {"supported": True, "items": items, "handler": store.setting("embed_url", "")}
    except AppError as e:
        return {"supported": True, "items": [], "error": e.message, "handler": store.setting("embed_url", "")}
