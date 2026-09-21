"""Фоновая обработка звонка: расшифровка и анализ идут в потоке, интерфейс не ждёт."""

import threading
import time

from .. import gemini, store
from ..db import dumps
from ..gemini import AppError
from . import pipeline

_slots = threading.Semaphore(4)   # не больше четырёх разборов одновременно
QUEUE_WAIT_SEC = 300              # столько ждём свободный слот, потом честно говорим об ошибке
MAX_JOB_SEC = 420                 # разбор дольше семи минут считаем зависшим


def _spawn(call_id: int, func, *args) -> None:
    """Запуск в фоновом потоке-демоне: перезапуск сервера не ждёт эти задачи."""
    def runner():
        if not _slots.acquire(timeout=QUEUE_WAIT_SEC):
            store.update_call(call_id, status="failed")
            _set(call_id, "error", "Сервер занят другими разборами. Попробуйте ещё раз через минуту.")
            return
        try:
            func(*args)
        finally:
            _slots.release()
    threading.Thread(target=runner, daemon=True, name="callbrief-job").start()
    _watch(call_id)


def _watch(call_id: int) -> None:
    """Сторож: если разбор завис, звонок не крутится вечно, а получает понятную ошибку."""
    def check():
        call = store.call(call_id)
        if call and call["status"] in ("transcribing", "analyzing"):
            store.update_call(call_id, status="failed")
            _set(call_id, "error", "Обработка заняла слишком много времени и была прервана. "
                                   "Проверьте интернет и VPN, затем попробуйте снова.")
    timer = threading.Timer(MAX_JOB_SEC, check)
    timer.daemon = True
    timer.start()

STAGES = {
    "transcribe": "Распознаю речь",
    "analyze": "Разбираю разговор",
    "done": "Готово",
    "error": "Ошибка",
}


def _set(call_id: int, stage: str, message: str = "", **extra) -> None:
    store.update_call(call_id, job=dumps({
        "stage": stage,
        "message": message or STAGES.get(stage, ""),
        "at": time.time(),
        **extra,
    }))


def process_audio(call_id: int, data: bytes, mime_type: str, filename: str) -> None:
    """Ставит звонок в очередь обработки и сразу возвращает управление."""
    _set(call_id, "transcribe", "Отправляю запись в Gemini")
    store.update_call(call_id, status="transcribing")
    _spawn(call_id, _run_audio, call_id, data, mime_type, filename)


def process_text(call_id: int) -> None:
    _set(call_id, "analyze")
    store.update_call(call_id, status="analyzing")
    _spawn(call_id, _run_analysis, call_id)


def _run_audio(call_id: int, data: bytes, mime_type: str, filename: str) -> None:
    started = time.time()
    last_save = [0.0]

    def on_chunk(text: str) -> None:
        # раз в полторы секунды сохраняем то, что уже распознано: пользователь видит текст в реальном времени
        now = time.time()
        if now - last_save[0] < 1.5:
            return
        last_save[0] = now
        store.update_call(call_id, transcript=text)
        _set(call_id, "transcribe", "Распознаю речь", chars=len(text), seconds=round(now - started))

    try:
        text, model = gemini.transcribe(data, mime_type, filename, on_chunk=on_chunk)
        store.update_call(call_id, transcript=text, model=model)
        # По голосу модель путает, кто говорит: уточняем роли по смыслу реплик
        _set(call_id, "transcribe", "Уточняю, где менеджер, а где клиент", seconds=round(time.time() - started))
        text, fixed = pipeline.fix_speakers(text)
        store.update_call(call_id, transcript=text, status="analyzing")
        _set(call_id, "analyze", "Разбираю разговор", seconds=round(time.time() - started))
        _run_analysis(call_id)
    except AppError as e:
        store.update_call(call_id, status="failed")
        _set(call_id, "error", e.message)
    except Exception as e:  # noqa: BLE001 — падение фоновой задачи не должно ронять сервер
        store.update_call(call_id, status="failed")
        _set(call_id, "error", f"Непредвиденная ошибка: {e}")


def _run_analysis(call_id: int) -> None:
    try:
        pipeline.analyze_call(call_id)
        _set(call_id, "done", "Разбор готов")
    except AppError as e:
        store.update_call(call_id, status="failed")
        _set(call_id, "error", e.message)
    except Exception as e:  # noqa: BLE001
        store.update_call(call_id, status="failed")
        _set(call_id, "error", f"Непредвиденная ошибка: {e}")
