"""Репозитории: единственное место, где приложение ходит в базу."""

from typing import Any

from . import db
from .db import dumps, loads

SEVERITY_ORDER = {"critical": 0, "attention": 1, "ok": 2}


# ---------- Пользователи ----------

def users(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM users"
    if active_only:
        sql += " WHERE active = 1"
    return db.query(sql + " ORDER BY role DESC, name")


def user(user_id: int) -> dict | None:
    return db.one("SELECT * FROM users WHERE id = ?", (user_id,))


def default_user() -> dict | None:
    return db.one("SELECT * FROM users WHERE active = 1 ORDER BY role DESC, id LIMIT 1")


# ---------- Клиенты ----------

def clients(owner_id: int | None = None) -> list[dict]:
    sql = """SELECT c.*, COUNT(k.id) AS calls_count, MAX(k.started_at) AS last_call_at
             FROM clients c LEFT JOIN calls k ON k.client_id = c.id"""
    params: list[Any] = []
    if owner_id:
        sql += " WHERE c.owner_id = ?"
        params.append(owner_id)
    sql += " GROUP BY c.id ORDER BY last_call_at DESC, c.name"
    return db.query(sql, params)


def client(client_id: int) -> dict | None:
    return db.one("SELECT * FROM clients WHERE id = ?", (client_id,))


def find_or_create_client(name: str, phone: str | None = None, company: str | None = None,
                          owner_id: int | None = None) -> int:
    if phone:
        found = db.one("SELECT id FROM clients WHERE phone = ?", (phone,))
        if found:
            return found["id"]
    found = db.one("SELECT id FROM clients WHERE name = ?", (name,))
    if found:
        return found["id"]
    return db.execute(
        "INSERT INTO clients (name, company, phone, owner_id) VALUES (?, ?, ?, ?)",
        (name, company, phone, owner_id),
    )


# ---------- Звонки ----------

CALL_COLUMNS = """k.*, u.name AS user_name, u.color AS user_color,
                  c.name AS client_name, c.company AS client_company"""

CALL_JOINS = "LEFT JOIN users u ON u.id = k.user_id LEFT JOIN clients c ON c.id = k.client_id"


def create_call(**fields) -> int:
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    return db.execute(f"INSERT INTO calls ({cols}) VALUES ({marks})", tuple(fields.values()))


def update_call(call_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE calls SET {sets} WHERE id = ?", (*fields.values(), call_id))


def call(call_id: int) -> dict | None:
    return db.one(
        f"SELECT {CALL_COLUMNS} FROM calls k {CALL_JOINS} WHERE k.id = ?", (call_id,)
    )


def calls(user_id: int | None = None, severity: str | None = None, search: str | None = None,
          flags: list[str] | None = None, days: int | None = None, limit: int = 100,
          offset: int = 0, visible_for: int | None = None) -> list[dict]:
    """Список звонков с фильтрами для раздела «Звонки».

    visible_for — id менеджера: он видит свои звонки и открытые звонки коллег.
    """
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    if user_id:
        where.append("k.user_id = ?")
        params.append(user_id)
    if visible_for:
        where.append("(k.user_id = ? OR k.shared = 1)")
        params.append(visible_for)
    if severity:
        where.append("k.severity = ?")
        params.append(severity)
    if days:
        where.append("k.started_at >= datetime('now', ?)")
        params.append(f"-{int(days)} days")
    if search:
        where.append("(k.title LIKE ? OR k.transcript LIKE ? OR c.name LIKE ?)")
        like = f"%{search}%"
        params += [like, like, like]
    for flag in flags or []:
        if flag == "no_next_step":
            where.append("k.has_next_step = 0")
        elif flag == "high_risk":
            where.append("k.risk_level = 'high'")
        elif flag == "refused":
            where.append("k.outcome LIKE '%отказ%'")
        elif flag == "interested":
            where.append("k.outcome LIKE '%интерес%'")
        elif flag in ("price", "competitor"):
            needle = "цен" if flag == "price" else "конкурент"
            where.append(
                "EXISTS (SELECT 1 FROM analyses a WHERE a.call_id = k.id AND lower(a.data) LIKE ?)"
            )
            params.append(f"%{needle}%")
    sql = (
        f"SELECT {CALL_COLUMNS} FROM calls k {CALL_JOINS} "
        f"WHERE {' AND '.join(where)} ORDER BY k.started_at DESC LIMIT ? OFFSET ?"
    )
    return db.query(sql, (*params, limit, offset))


def delete_call(call_id: int) -> None:
    db.execute("DELETE FROM calls WHERE id = ?", (call_id,))


# ---------- Анализ и scorecard ----------

def save_analysis(call_id: int, data: dict, confirmed: int, total: int, model: str) -> None:
    db.execute(
        "INSERT INTO analyses (call_id, data, confirmed, total, model) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(call_id) DO UPDATE SET data = excluded.data, confirmed = excluded.confirmed, "
        "total = excluded.total, model = excluded.model, created_at = datetime('now')",
        (call_id, dumps(data), confirmed, total, model),
    )


def analysis(call_id: int) -> dict | None:
    row = db.one("SELECT * FROM analyses WHERE call_id = ?", (call_id,))
    if row:
        row["data"] = loads(row["data"], {})
    return row


def save_scorecard(call_id: int, data: dict, total: float, model: str) -> None:
    db.execute(
        "INSERT INTO scorecards (call_id, data, total, model) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(call_id) DO UPDATE SET data = excluded.data, total = excluded.total, "
        "model = excluded.model, created_at = datetime('now')",
        (call_id, dumps(data), total, model),
    )


def scorecard(call_id: int) -> dict | None:
    row = db.one("SELECT * FROM scorecards WHERE call_id = ?", (call_id,))
    if row:
        row["data"] = loads(row["data"], {})
    return row


# ---------- Тренер ----------

def replace_coach_items(call_id: int, user_id: int | None, items: list[dict]) -> None:
    db.execute("DELETE FROM coach_items WHERE call_id = ?", (call_id,))
    if not items:
        return
    db.execute_many(
        "INSERT INTO coach_items (call_id, user_id, time_sec, skill, what_happened, why_problem,"
        " better_action, sample_phrase, quote, verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (call_id, user_id, i.get("time_sec"), i.get("skill", ""), i.get("what_happened", ""),
             i.get("why_problem", ""), i.get("better_action", ""), i.get("sample_phrase"),
             i.get("quote"), int(bool(i.get("verified"))))
            for i in items
        ],
    )


def coach_items(call_id: int | None = None, user_id: int | None = None, days: int | None = None,
                limit: int = 200) -> list[dict]:
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    if call_id:
        where.append("ci.call_id = ?")
        params.append(call_id)
    if user_id:
        where.append("ci.user_id = ?")
        params.append(user_id)
    if days:
        where.append("k.started_at >= datetime('now', ?)")
        params.append(f"-{int(days)} days")
    return db.query(
        "SELECT ci.*, k.title AS call_title, k.started_at FROM coach_items ci "
        f"JOIN calls k ON k.id = ci.call_id WHERE {' AND '.join(where)} "
        "ORDER BY k.started_at DESC LIMIT ?",
        (*params, limit),
    )


def replace_best_moments(call_id: int, user_id: int | None, items: list[dict]) -> None:
    db.execute("DELETE FROM best_moments WHERE call_id = ? AND pinned = 0", (call_id,))
    if not items:
        return
    db.execute_many(
        "INSERT INTO best_moments (call_id, user_id, skill, score, time_sec, quote, why_good)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (call_id, user_id, i.get("skill", ""), i.get("score"), i.get("time_sec"),
             i.get("quote", ""), i.get("why_good"))
            for i in items
        ],
    )


def best_moments(skill: str | None = None, limit: int = 50) -> list[dict]:
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    if skill:
        where.append("b.skill = ?")
        params.append(skill)
    return db.query(
        "SELECT b.*, u.name AS user_name, u.color AS user_color, k.title AS call_title "
        "FROM best_moments b LEFT JOIN users u ON u.id = b.user_id "
        f"JOIN calls k ON k.id = b.call_id WHERE {' AND '.join(where)} "
        "ORDER BY b.pinned DESC, b.score DESC LIMIT ?",
        (*params, limit),
    )


# ---------- Действия ----------

def replace_actions(call_id: int, items: list[dict]) -> None:
    db.execute("DELETE FROM actions WHERE call_id = ? AND status = 'draft'", (call_id,))
    db.execute_many(
        "INSERT INTO actions (call_id, type, payload) VALUES (?, ?, ?)",
        [(call_id, i["type"], dumps(i.get("payload", {}))) for i in items],
    )


def actions(call_id: int | None = None, status: str | None = None) -> list[dict]:
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    if call_id:
        where.append("a.call_id = ?")
        params.append(call_id)
    if status:
        where.append("a.status = ?")
        params.append(status)
    rows = db.query(
        "SELECT a.*, k.title AS call_title, k.user_id FROM actions a "
        f"JOIN calls k ON k.id = a.call_id WHERE {' AND '.join(where)} ORDER BY a.id",
        params,
    )
    for row in rows:
        row["payload"] = loads(row["payload"], {})
    return rows


def action(action_id: int) -> dict | None:
    row = db.one("SELECT * FROM actions WHERE id = ?", (action_id,))
    if row:
        row["payload"] = loads(row["payload"], {})
    return row


def update_action(action_id: int, **fields) -> None:
    if "payload" in fields:
        fields["payload"] = dumps(fields["payload"])
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE actions SET {sets} WHERE id = ?", (*fields.values(), action_id))


# ---------- Настройки ----------

def setting(key: str, default: Any = None) -> Any:
    row = db.one("SELECT value FROM settings WHERE key = ?", (key,))
    return loads(row["value"], default) if row else default


def set_setting(key: str, value: Any) -> None:
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, dumps(value)),
    )
