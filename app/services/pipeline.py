"""Конвейер обработки звонка: транскрипт → анализ + оценка → проверка цитат → действия для CRM."""

import threading

from .. import gemini, speakers, store
from ..gemini import AppError
from ..verify import find_quote, verify_result
from . import severity as sev

MIN_TEXT_LEN = 30
MAX_TEXT_LEN = 200_000
SCORE_WAIT_SEC = 120   # дольше ждать оценку бессмысленно: сохраняем разбор без неё

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def _max_risk(data: dict) -> str:
    risks = data.get("risks") or []
    if not risks:
        return "none"
    return sorted(risks, key=lambda r: RISK_ORDER.get(r.get("level"), 3))[0].get("level", "none")


def check_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) < MIN_TEXT_LEN:
        raise AppError("empty_text", "Вставьте текст разговора — сейчас он пустой или слишком короткий.", 400)
    if len(text) > MAX_TEXT_LEN:
        raise AppError("too_long", f"Текст слишком длинный ({len(text)} символов). Максимум — {MAX_TEXT_LEN}.", 400)
    return text


def _build_actions(call: dict, data: dict) -> list[dict]:
    """Готовит развёрнутый комментарий, задачу и следующий контакт — то, что уйдёт в CRM одной кнопкой."""
    header_bits = [b for b in (call.get("client_company") or call.get("client_name"), data.get("contact_name")) if b]
    # Первой строкой — итог и риск: менеджеру видно главное, не читая весь текст
    marks = [m for m in (data.get("outcome"),) if m]
    if any(r.get("level") == "high" for r in data.get("risks", [])):
        marks.append("высокий риск")
    lines = []
    if header_bits:
        lines.append(" · ".join(header_bits))
    if marks:
        lines.append("Итог звонка: " + " · ".join(marks))
    comment = ("\n".join(lines) + "\n\n" if lines else "") + (data.get("crm_comment") or data.get("summary", ""))
    items = [{"type": "crm_comment", "payload": {"text": comment}}]

    steps = data.get("next_steps") or []
    step = steps[0] if steps else None
    if step:
        items.append({"type": "task", "payload": {
            "title": step["action"], "owner": step.get("owner"), "deadline": step.get("deadline"),
        }})
        items.append({"type": "next_contact", "payload": {"when": step.get("deadline") or "в ближайшее время"}})
    else:
        items.append({"type": "task", "payload": {"title": "Назначить следующий контакт с клиентом", "deadline": None}})

    return items


def _in_background(func, *args):
    """Запускает вызов модели в отдельном потоке: анализ и оценка идут параллельно."""
    box: dict = {}

    def runner():
        try:
            box["value"] = func(*args)
        except Exception as e:  # noqa: BLE001 — исключение пробрасываем в вызывающий поток
            box["error"] = e

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread, box


def _score_call(call_id: int, text: str, user_id: int | None, result_box: dict) -> float | None:
    """Раскладывает готовый ответ модели: оценка по критериям, разбор ошибок, лучшие моменты."""
    if "value" not in result_box:
        return None  # оценка не удалась — анализ всё равно сохраняем
    result, model = result_box["value"]
    data = result.model_dump()

    coach_items = []
    for item in data["coach_items"]:
        item["verified"] = find_quote(item["quote"], text)
        coach_items.append(item)
    best_moments = [m for m in data["best_moments"] if find_quote(m["quote"], text)]

    total = round(sum(c["score"] for c in data["criteria"]) / len(data["criteria"]), 1) if data["criteria"] else None
    store.save_scorecard(call_id, {
        "criteria": data["criteria"], "strengths": data["strengths"],
        "blockers": data["blockers"], "growth_area": data["growth_area"],
        "general_advice": data.get("general_advice", []),
    }, total or 0, model)
    store.replace_coach_items(call_id, user_id, coach_items)
    store.replace_best_moments(call_id, user_id, best_moments)
    return total


def analyze_call(call_id: int) -> dict:
    """Анализирует транскрипт звонка: договорённости, оценка менеджера, действия для CRM."""
    call = store.call(call_id)
    if not call:
        raise AppError("not_found", "Звонок не найден.", 404)
    text = check_text(call["transcript"])

    # Оба вызова модели идут одновременно: разбор ждёт максимум из двух, а не их сумму
    score_thread, score_box = _in_background(gemini.score, text)
    result, model = gemini.analyze(text)
    response = verify_result(result, text, model)
    data = response.model_dump()

    score_thread.join(timeout=SCORE_WAIT_SEC)   # оценка не должна задерживать разбор
    total = _score_call(call_id, text, call["user_id"], score_box)
    has_next_step = bool(data.get("next_steps"))
    level, reason = sev.compute(data, total, has_next_step)

    store.save_analysis(call_id, data, response.verification.confirmed, response.verification.total, model)
    store.replace_actions(call_id, _build_actions(call, data))
    store.update_call(
        call_id,
        status="analyzed",
        model=model,
        has_next_step=int(has_next_step),
        risk_level=_max_risk(data),
        severity=level,
        severity_reason=reason,
        score=total,
        title=call["title"] or "Разговор",
    )
    return data


def fix_speakers(transcript: str) -> tuple[str, int]:
    """Уточняет метки «Менеджер/Клиент» по смыслу реплик. Возвращает текст и число исправленных строк.

    Если модель недоступна или ответила неполно — оставляем расшифровку как есть:
    лучше исходные метки, чем сорванная обработка звонка.
    """
    rows = speakers.parse(transcript)
    if sum(1 for r in rows if r["speaker"]) < 2:
        return transcript, 0
    try:
        result, _ = gemini.fix_speakers(speakers.numbered(rows))
    except AppError:
        return transcript, 0
    fixes = [f.model_dump() for f in result.lines]
    return speakers.render(speakers.apply(rows, fixes)), speakers.changed_count(rows, fixes)


def transcribe_audio(data: bytes, mime_type: str, filename: str, on_chunk=None) -> tuple[str, str]:
    """Расшифровка аудио — обёртка над Gemini, чтобы роутеры не знали о деталях."""
    return gemini.transcribe(data, mime_type, filename, on_chunk=on_chunk)
