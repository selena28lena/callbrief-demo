"""Встраиваемая панель CallBrief внутри карточки сделки Битрикс24."""

import json
import uuid

import httpx
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from .. import db, store
from ..crm import base as crm_base
from ..gemini import AppError
from ..services import jobs
from ..session import current_user
from .calls import AUDIO_TYPES, MAX_AUDIO_BYTES

router = APIRouter(tags=["embed"])

PLACEMENTS = [
    ("CRM_DEAL_DETAIL_TAB", "CallBrief"),
    ("CRM_DEAL_DETAIL_TOOLBAR", "CallBrief — разбор звонка"),
]


STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def _deal_id_from_form(form) -> str:
    """Битрикс присылает параметры встраивания в поле PLACEMENT_OPTIONS."""
    raw = form.get("PLACEMENT_OPTIONS")
    if raw:
        try:
            options = json.loads(raw)
            return str(options.get("ID") or options.get("id") or "")
        except (TypeError, ValueError):
            return ""
    return str(form.get("deal_id") or "")


def _debug_log(text: str) -> None:
    try:
        with open(db.DATA_DIR / "embed_debug.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def _try_register_placements(auth: str, domain: str, handler: str) -> list[str]:
    """Если кнопка ещё не зарегистрирована в этом портале — регистрирует её сейчас."""
    if store.setting("embed_url") == handler:
        return []
    done = []
    base = f"https://{domain}/rest"
    for code, title in PLACEMENTS:
        try:
            httpx.post(f"{base}/placement.unbind.json", data={"auth": auth, "PLACEMENT": code, "HANDLER": handler}, timeout=15)
        except httpx.HTTPError:
            pass
        try:
            r = httpx.post(f"{base}/placement.bind.json", data={
                "auth": auth, "PLACEMENT": code, "HANDLER": handler, "TITLE": title,
                "DESCRIPTION": "AI-разбор звонка: комментарий и задача в один клик",
            }, timeout=15)
            body = r.json()
            _debug_log(f"bind {code}: {body}")
            if body.get("result"):
                done.append(code)
        except httpx.HTTPError as e:
            _debug_log(f"bind {code} ошибка сети: {e}")
    if done:
        store.set_setting("embed_url", handler)
    try:
        listing = httpx.post(f"{base}/placement.list.json", data={"auth": auth}, timeout=15).json()
        _debug_log(f"placement.list после привязки: {listing}")
    except httpx.HTTPError as e:
        _debug_log(f"placement.list ошибка сети: {e}")
    return done


@router.api_route("/embed", methods=["GET", "POST"], include_in_schema=False)
async def embed_page(request: Request):
    deal_id = request.query_params.get("deal_id", "")
    if request.method == "POST":
        form = await request.form()
        deal_id = _deal_id_from_form(form) or deal_id
        auth = form.get("AUTH_ID")
        domain = form.get("DOMAIN") or request.query_params.get("DOMAIN")
        _debug_log("keys=" + ",".join(form.keys()) + " | query=" + str(dict(request.query_params)))
        if auth and domain:
            host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            _try_register_placements(auth, domain, f"https://{host}/embed")
    from ..main import NO_CACHE, build_token   # локальный импорт: иначе циклическая зависимость

    html = (STATIC_DIR / "embed.html").read_text(encoding="utf-8")
    html = html.replace("__DEAL_ID__", deal_id)
    html = html.replace("/static/", f"/s/{build_token()}/")
    return HTMLResponse(html, headers=NO_CACHE)


def _client_for_deal(deal_id: str, user: dict) -> dict:
    """Находит или создаёт клиента, привязанного к сделке CRM."""
    row = db.one("SELECT * FROM clients WHERE crm_id = ?", (deal_id,))
    if row:
        return row
    crm = crm_base.get_adapter()
    deal = crm.get_deal(deal_id) or {}
    contact = deal.get("contact") or {}
    client_id = db.execute(
        "INSERT INTO clients (name, company, phone, crm_id, crm_kind, stage, owner_id) "
        "VALUES (?, ?, ?, ?, 'deal', ?, ?)",
        (contact.get("name") or "Контакт", deal.get("title") or f"Сделка {deal_id}",
         contact.get("phone"), deal_id, deal.get("stage"), user["id"]),
    )
    return store.client(client_id)


@router.get("/api/embed/deal/{deal_id}")
def embed_deal(deal_id: str, user: dict = Depends(current_user)):
    """Данные для панели: сделка, её звонки и последний разбор."""
    crm = crm_base.get_adapter()
    try:
        deal = crm.get_deal(deal_id)
    except AppError:
        deal = None
    client = db.one("SELECT * FROM clients WHERE crm_id = ?", (deal_id,))
    # Звонки именно этой карточки: один и тот же файл могли загружать в разные сделки
    calls = db.query(
        "SELECT k.*, u.name AS user_name FROM calls k LEFT JOIN users u ON u.id = k.user_id "
        "WHERE k.crm_deal_id = ? ORDER BY k.started_at DESC LIMIT 10",
        (deal_id,),
    )
    if not calls and client:
        calls = db.query(
            "SELECT k.*, u.name AS user_name FROM calls k LEFT JOIN users u ON u.id = k.user_id "
            "WHERE k.client_id = ? AND k.crm_deal_id IS NULL ORDER BY k.started_at DESC LIMIT 10",
            (client["id"],),
        )
    last = calls[0] if calls else None
    analysis = store.analysis(last["id"])["data"] if last and store.analysis(last["id"]) else None
    return {
        "deal": deal,
        "client": client,
        "calls": calls,
        "last_call": last,
        "analysis": analysis,
        "actions": store.actions(call_id=last["id"], status="draft") if last else [],
        "provider": crm.title,
    }


@router.post("/api/embed/upload")
def embed_upload(deal_id: str = Form(...), file: UploadFile = File(...), user: dict = Depends(current_user)):
    """Загрузка записи прямо из карточки сделки: расшифровка и разбор идут в фоне."""
    filename = file.filename or "audio"
    suffix = Path(filename).suffix.lower()
    mime_type = AUDIO_TYPES.get(suffix)
    if not mime_type:
        raise AppError("bad_format", "Поддерживаются файлы mp3, wav, m4a и ogg.", 400)
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise AppError("empty_file", "Файл пустой.", 400)

    client = _client_for_deal(deal_id, user)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (db.AUDIO_DIR / stored_name).write_bytes(data)
    call_id = store.create_call(
        user_id=user["id"], client_id=client["id"], title=filename,
        source="crm", audio_path=stored_name, transcript="", crm_deal_id=deal_id,
    )
    jobs.process_audio(call_id, data, mime_type, filename)
    return {"call_id": call_id, "status": "transcribing"}


@router.post("/api/embed/text")
def embed_text(deal_id: str = Form(...), text: str = Form(...), user: dict = Depends(current_user)):
    client = _client_for_deal(deal_id, user)
    call_id = store.create_call(
        user_id=user["id"], client_id=client["id"], title=f"Разговор · сделка {deal_id}",
        source="crm", transcript=text.strip(), crm_deal_id=deal_id,
    )
    jobs.process_text(call_id)
    return {"call_id": call_id, "status": "analyzing"}


INSTALL_DONE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<script src="//api.bitrix24.com/api/v1/"></script></head>
<body style="font:16px system-ui;background:#0a0e1a;color:#f8fafc;padding:24px">
<h2>CallBrief установлен</h2><p>__TEXT__</p>
<script>if (window.BX24) BX24.init(function () { BX24.installFinish(); });</script>
</body></html>"""


@router.api_route("/bitrix/install", methods=["GET", "POST"], include_in_schema=False)
async def bitrix_install(request: Request):
    """Установка локального приложения: регистрируем вкладку и кнопку в карточке сделки."""
    form = await request.form() if request.method == "POST" else {}
    auth = form.get("AUTH_ID") or request.query_params.get("AUTH_ID")
    domain = form.get("DOMAIN") or request.query_params.get("DOMAIN")
    if not auth or not domain:
        return HTMLResponse(INSTALL_DONE.replace("__TEXT__", "Не пришли данные авторизации от Битрикс24."), 400)

    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    handler = f"https://{host}/embed"
    done = []
    for code, title in PLACEMENTS:
        base = f"https://{domain}/rest"
        httpx.post(f"{base}/placement.unbind.json", data={"auth": auth, "PLACEMENT": code, "HANDLER": handler}, timeout=20)
        r = httpx.post(f"{base}/placement.bind.json", data={
            "auth": auth, "PLACEMENT": code, "HANDLER": handler, "TITLE": title,
            "DESCRIPTION": "AI-разбор звонка: комментарий и задача в один клик",
        }, timeout=20)
        if r.json().get("result"):
            done.append(code)
    store.set_setting("embed_url", handler)
    text = f"Кнопки добавлены: {', '.join(done) or 'нет'}. Откройте любую сделку — там появится вкладка CallBrief."
    return HTMLResponse(INSTALL_DONE.replace("__TEXT__", text))
