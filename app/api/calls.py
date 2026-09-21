"""Звонки: список, карточка, загрузка аудио, запуск анализа."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db, store
from ..gemini import AppError
from ..services import jobs, pipeline
from ..session import current_user, is_head

router = APIRouter(prefix="/api", tags=["calls"])

AUDIO_TYPES = {".mp3": "audio/mp3", ".wav": "audio/wav", ".m4a": "audio/aac", ".ogg": "audio/ogg"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024


class CallCreate(BaseModel):
    text: str = ""
    title: str | None = None
    client_name: str | None = None
    source: str = "text"
    duration: float | None = None
    audio_path: str | None = None


class TranscriptUpdate(BaseModel):
    text: str


def _call_or_404(call_id: int) -> dict:
    call = store.call(call_id)
    if not call:
        raise AppError("not_found", "Звонок не найден.", 404)
    return call


def _new_call(user: dict, payload: CallCreate) -> int:
    client_id = None
    if payload.client_name:
        client_id = store.find_or_create_client(payload.client_name.strip(), owner_id=user["id"])
    return store.create_call(
        user_id=user["id"],
        client_id=client_id,
        title=(payload.title or "Разговор").strip()[:120],
        transcript=payload.text.strip(),
        source=payload.source,
        duration=payload.duration,
        audio_path=payload.audio_path,
    )


@router.get("/calls")
def list_calls(user: dict = Depends(current_user), mine: bool = False, severity: str | None = None,
               q: str | None = None, flags: str | None = None, days: int | None = None,
               limit: int = 100, offset: int = 0):
    rows = store.calls(
        user_id=user["id"] if mine else None,
        severity=severity,
        search=q,
        flags=[f for f in (flags or "").split(",") if f],
        days=days,
        limit=min(limit, 500),
        offset=offset,
        visible_for=None if is_head(user) else user["id"],
    )
    return {"items": rows}


@router.post("/calls")
def create_call(payload: CallCreate, user: dict = Depends(current_user)):
    pipeline.check_text(payload.text)
    call_id = _new_call(user, payload)
    jobs.process_text(call_id)
    return {"id": call_id, "call": store.call(call_id), "status": "analyzing"}


@router.get("/calls/{call_id}")
def get_call(call_id: int, user: dict = Depends(current_user)):
    call = _call_or_404(call_id)
    analysis = store.analysis(call_id)
    scorecard = store.scorecard(call_id)
    return {
        "call": call,
        "job": db.loads(call.get("job"), None),
        "analysis": analysis["data"] if analysis else None,
        "verification": {"confirmed": analysis["confirmed"], "total": analysis["total"]} if analysis else None,
        "scorecard": scorecard["data"] if scorecard else None,
        "coach_items": store.coach_items(call_id=call_id),
        "actions": store.actions(call_id=call_id),
        "can_manage": is_head(user) or call["user_id"] == user["id"],
    }


@router.put("/calls/{call_id}/transcript")
def update_transcript(call_id: int, payload: TranscriptUpdate, user: dict = Depends(current_user)):
    _call_or_404(call_id)
    store.update_call(call_id, transcript=payload.text.strip())
    return {"ok": True}


@router.post("/calls/{call_id}/analyze")
def analyze_call(call_id: int, user: dict = Depends(current_user)):
    """Запускает (повторный) разбор в фоне: экран звонка сам покажет прогресс."""
    call = _call_or_404(call_id)
    pipeline.check_text(call["transcript"])
    jobs.process_text(call_id)
    return {"call_id": call_id, "status": "analyzing"}


@router.post("/calls/upload")
def upload_audio(file: UploadFile = File(...), user: dict = Depends(current_user)):
    """Загружает запись, расшифровывает её и создаёт звонок со статусом «новый»."""
    filename = file.filename or "audio"
    suffix = Path(filename).suffix.lower()
    mime_type = AUDIO_TYPES.get(suffix)
    if not mime_type:
        raise AppError("bad_format", "Поддерживаются только файлы mp3, wav, m4a и ogg.", 400)
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise AppError("empty_file", "Файл пустой.", 400)
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError("too_large", "Файл больше 200 МБ. Сожмите запись или разделите её на части.", 413)

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (db.AUDIO_DIR / stored_name).write_bytes(data)

    call_id = _new_call(user, CallCreate(text="", title=filename, source="upload", audio_path=stored_name))
    jobs.process_audio(call_id, data, mime_type, filename)
    return {"id": call_id, "call": store.call(call_id), "status": "transcribing"}


@router.get("/calls/{call_id}/audio")
def get_audio(call_id: int, user: dict = Depends(current_user)):
    call = _call_or_404(call_id)
    if not call["audio_path"]:
        raise AppError("no_audio", "К этому звонку не приложена запись.", 404)
    path = db.AUDIO_DIR / call["audio_path"]
    if not path.exists():
        raise AppError("no_audio", "Файл записи не найден на сервере.", 404)
    return FileResponse(path, media_type=AUDIO_TYPES.get(path.suffix.lower(), "audio/mpeg"))


@router.delete("/calls/{call_id}")
def delete_call(call_id: int, user: dict = Depends(current_user)):
    call = _call_or_404(call_id)
    if not (is_head(user) or call["user_id"] == user["id"]):
        raise AppError("forbidden", "Удалять чужие звонки может только руководитель.", 403)
    if call["audio_path"]:
        (db.AUDIO_DIR / call["audio_path"]).unlink(missing_ok=True)
    store.delete_call(call_id)
    return {"ok": True}
