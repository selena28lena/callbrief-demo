"""Подключение к SQLite и инициализация схемы. Никаких внешних зависимостей."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "callbrief.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_lock = threading.Lock()

DEFAULT_USERS = [
    ("Алексей Соколов", "head", "#34d399", "head.jpg", "Руководитель отдела продаж"),
    ("Иван Петров", "manager", "#818cf8", "ivan.jpg", "Менеджер по продажам"),
    ("Алексей Смирнов", "manager", "#38bdf8", "alexey.jpg", "Менеджер по продажам"),
    ("Дмитрий Орлов", "manager", "#fbbf24", "dmitry.jpg", "Менеджер по продажам"),
    ("Сергей Иванов", "manager", "#fb7185", "sergey.jpg", "Менеджер по продажам"),
    ("Ольга Кравцова", "manager", "#a78bfa", "olga.jpg", "Старший менеджер"),
]


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    """Соединение на время операции: пишем под блокировкой, читаем параллельно."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params: Iterable = ()) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: Iterable = (), default: Any = None) -> Any:
    row = one(sql, params)
    return next(iter(row.values())) if row else default


def execute(sql: str, params: Iterable = ()) -> int:
    with _lock, db() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def execute_many(sql: str, rows: Iterable[Iterable]) -> None:
    with _lock, db() as conn:
        conn.executemany(sql, [tuple(r) for r in rows])


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: Any, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Простая миграция: добавляет недостающие колонки в уже созданные таблицы."""
    wanted = {
        "users": [("avatar", "TEXT"), ("title", "TEXT")],
        "clients": [("industry", "TEXT"), ("status", "TEXT")],
        "calls": [("job", "TEXT"), ("crm_deal_id", "TEXT")],
    }
    for table, columns in wanted.items():
        have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def init_db() -> None:
    """Создаёт таблицы и наполняет справочник пользователей при первом запуске."""
    with _lock, db() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_columns(conn)
        empty = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
        if empty:
            conn.executemany(
                "INSERT INTO users (name, role, color, avatar, title) VALUES (?, ?, ?, ?, ?)",
                DEFAULT_USERS,
            )
