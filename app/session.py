"""Текущий пользователь: берём из заголовка X-User-Id, без паролей."""

from fastapi import Header

from . import store
from .gemini import AppError


def current_user(x_user_id: str | None = Header(default=None)) -> dict:
    user = store.user(int(x_user_id)) if x_user_id and x_user_id.isdigit() else None
    user = user or store.default_user()
    if not user:
        raise AppError("no_user", "В системе нет ни одного пользователя.", 500)
    return user


def is_head(user: dict) -> bool:
    return user.get("role") == "head"


def require_head(user: dict) -> None:
    if not is_head(user):
        raise AppError("forbidden", "Раздел доступен только руководителю.", 403)
