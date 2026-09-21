"""Аналитика и разделы: статистика, команда, клиенты, действия, тренер, инсайты."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db, store
from ..gemini import AppError
from ..services import stats
from ..session import current_user, is_head, require_head

router = APIRouter(prefix="/api", tags=["analytics"])


class ActionPayload(BaseModel):
    payload: dict


@router.get("/stats")
def get_stats(days: int = 30, mine: bool = False, user: dict = Depends(current_user)):
    return stats.overview(days=days, user_id=user["id"] if mine else None)


@router.get("/team")
def get_team(days: int = 30, user: dict = Depends(current_user)):
    require_head(user)
    return stats.team(days=days)


@router.get("/insights")
def get_insights(days: int = 30, user: dict = Depends(current_user)):
    require_head(user)
    return {"items": stats.insights(days=days)}


@router.get("/coach")
def get_coach(days: int = 30, user_id: int | None = None, user: dict = Depends(current_user)):
    target = user_id if (user_id and is_head(user)) else user["id"]
    data = stats.coach_summary(target, days=days)
    data["user"] = store.user(target)
    return data


@router.get("/best")
def get_best(skill: str | None = None, user: dict = Depends(current_user)):
    moments = store.best_moments(skill=skill, limit=60)
    skills = db.query("SELECT skill, COUNT(*) AS n FROM best_moments GROUP BY skill ORDER BY n DESC")
    return {"items": moments, "skills": skills}


@router.get("/clients")
def get_clients(user: dict = Depends(current_user)):
    rows = db.query(
        "SELECT c.*, u.name AS owner_name, u.avatar AS owner_avatar, COUNT(k.id) AS calls_count, "
        "MAX(k.started_at) AS last_call_at, "
        "SUM(CASE WHEN k.severity = 'critical' THEN 1 ELSE 0 END) AS critical, "
        "MAX(CASE WHEN k.has_next_step = 1 THEN 1 ELSE 0 END) AS has_next_step "
        "FROM clients c LEFT JOIN calls k ON k.client_id = c.id LEFT JOIN users u ON u.id = c.owner_id "
        "GROUP BY c.id ORDER BY critical DESC, last_call_at DESC"
    )
    return {"items": rows}


@router.get("/clients/{client_id}")
def get_client(client_id: int, user: dict = Depends(current_user)):
    client = store.client(client_id)
    if not client:
        raise AppError("not_found", "Клиент не найден.", 404)
    calls = db.query(
        "SELECT k.*, u.name AS user_name, u.avatar AS user_avatar FROM calls k "
        "LEFT JOIN users u ON u.id = k.user_id WHERE k.client_id = ? ORDER BY k.started_at DESC",
        (client_id,),
    )
    agreements, risks = [], []
    for call in calls:
        analysis = store.analysis(call["id"])
        if not analysis:
            continue
        data = analysis["data"]
        for item in data.get("agreements", []):
            agreements.append({**item, "call_id": call["id"], "started_at": call["started_at"]})
        for item in data.get("risks", []):
            if item.get("level") in ("high", "medium"):
                risks.append({**item, "call_id": call["id"]})
    return {"client": client, "calls": calls, "agreements": agreements[:8], "risks": risks[:8]}


@router.get("/actions")
def get_actions(status: str = "draft", user: dict = Depends(current_user)):
    """Очередь действий: сгруппирована по звонкам, чтобы менеджер шёл по списку."""
    rows = db.query(
        "SELECT a.*, k.title AS call_title, k.client_id, k.user_id, k.severity, k.started_at, "
        "c.company AS client_company, c.name AS client_name, c.crm_id, u.name AS user_name "
        "FROM actions a JOIN calls k ON k.id = a.call_id "
        "LEFT JOIN clients c ON c.id = k.client_id LEFT JOIN users u ON u.id = k.user_id "
        "WHERE a.status = ? " + ("" if is_head(user) else "AND k.user_id = ? ") +
        "ORDER BY k.started_at DESC, a.id",
        (status,) if is_head(user) else (status, user["id"]),
    )
    grouped: dict[int, dict] = {}
    for row in rows:
        row["payload"] = db.loads(row["payload"], {})
        group = grouped.setdefault(row["call_id"], {
            "call_id": row["call_id"],
            "call_title": row["call_title"],
            "client": row["client_company"] or row["client_name"] or row["call_title"],
            "contact": row["client_name"],
            "user_name": row["user_name"],
            "severity": row["severity"],
            "started_at": row["started_at"],
            "crm_id": row["crm_id"],
            "actions": [],
        })
        group["actions"].append(row)
    return {"items": list(grouped.values())}


@router.put("/actions/{action_id}")
def update_action(action_id: int, body: ActionPayload, user: dict = Depends(current_user)):
    if not store.action(action_id):
        raise AppError("not_found", "Действие не найдено.", 404)
    store.update_action(action_id, payload=body.payload)
    return {"ok": True}


@router.post("/actions/{action_id}/skip")
def skip_action(action_id: int, user: dict = Depends(current_user)):
    store.update_action(action_id, status="skipped")
    return {"ok": True}
