"""Общие маршруты: состояние подключения, сессия пользователя, примеры разговоров."""

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import gemini, store
from ..services import demo_data
from ..gemini import AppError
from ..session import current_user

router = APIRouter(prefix="/api", tags=["meta"])

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
EXAMPLE_FILES = {1: "1_success.txt", 2: "2_vague.txt", 3: "3_long.txt"}
EXAMPLE_TITLES = {1: "Пример 1 · Успешный", 2: "Пример 2 · Размытый", 3: "Пример 3 · Длинный"}


class UserSwitch(BaseModel):
    user_id: int


@router.get("/health")
def health():
    return {"has_key": bool(gemini.get_api_key()), "model": gemini.get_model()}


@router.get("/session")
def session(user: dict = Depends(current_user)):
    return {"user": user, "users": store.users()}


@router.get("/examples/{n}")
def example(n: int):
    name = EXAMPLE_FILES.get(n)
    if not name:
        raise AppError("not_found", "Такого примера нет. Доступны примеры 1, 2 и 3.", 404)
    return {"text": (EXAMPLES_DIR / name).read_text(encoding="utf-8"), "title": EXAMPLE_TITLES[n]}


@router.post("/demo/seed")
def seed_demo(user: dict = Depends(current_user)):
    """Наполняет базу демонстрационным отделом продаж."""
    return demo_data.seed()


@router.delete("/demo")
def clear_demo(user: dict = Depends(current_user)):
    demo_data.clear()
    return {"ok": True}
