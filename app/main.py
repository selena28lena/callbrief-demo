"""CallBrief — FastAPI-приложение."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from . import db, store
from .api import analytics as analytics_api
from .api import calls as calls_api
from .api import crm as crm_api
from .api import embed as embed_api
from .api import meta as meta_api
from .db import init_db
from .gemini import AppError
from .services import demo_data

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv(BASE_DIR / ".env", override=True)   # ключи и адрес CRM доступны всему приложению
    init_db()
    # При первом запуске база пустая — наполняем демо-отделом, чтобы все разделы было что показать.
    # Если демо-данные удалили в настройках вручную, больше не подкладываем их.
    if not db.scalar("SELECT COUNT(*) FROM calls", default=0) and store.setting("demo_cleared") != "1":
        demo_data.seed(reset=False)
    yield


class NoCacheStatic(StaticFiles):
    """Отдаёт стили и скрипты без кеша.

    no-store, а не no-cache: браузер не имеет права хранить старую копию модуля,
    иначе интерфейс обновляется только после ручной очистки кеша.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response


def build_token() -> str:
    """Метка версии статики — самое свежее время правки файлов.

    Chrome не перезапрашивает модули, подгружаемые через import(), даже по Ctrl+Shift+R.
    Поэтому адреса меняются вместе с файлами: браузер обязан скачать всё заново.
    """
    newest = 0.0
    for path in STATIC_DIR.rglob("*"):
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return str(int(newest))


app = FastAPI(title="CallBrief", lifespan=lifespan)
app.mount("/static", NoCacheStatic(directory=STATIC_DIR), name="static")
app.include_router(meta_api.router)
app.include_router(calls_api.router)
app.include_router(analytics_api.router)
app.include_router(crm_api.router)
app.include_router(embed_api.router)


@app.exception_handler(AppError)
def app_error_handler(_: Request, exc: AppError):
    return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
def validation_error_handler(_: Request, __: RequestValidationError):
    return JSONResponse(
        {"error": "bad_request", "message": "Некорректный запрос к серверу."}, status_code=422
    )


NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"}


def page(name: str) -> HTMLResponse:
    """Отдаёт страницу, подставив метку версии во все ссылки на статику."""
    html = (STATIC_DIR / name).read_text(encoding="utf-8")
    html = html.replace("/static/", f"/s/{build_token()}/")
    return HTMLResponse(html, headers=NO_CACHE)


@app.get("/s/{version}/{path:path}", include_in_schema=False)
def versioned_static(version: str, path: str):
    """Та же статика, но по адресу с меткой версии — старый кеш браузера к ней не подходит."""
    target = (STATIC_DIR / path).resolve()
    if not target.is_file() or STATIC_DIR.resolve() not in target.parents:
        raise AppError("not_found", "Файл не найден.", 404)
    return FileResponse(target, headers=NO_CACHE)


@app.get("/", include_in_schema=False)
def index():
    return page("index.html")


@app.get("/app", include_in_schema=False)
def workspace():
    """Рабочее приложение: сайдбар, звонки, разборы."""
    return page("app.html")
