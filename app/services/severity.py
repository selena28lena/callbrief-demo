"""Критичность звонка считается правилами, без обращения к AI."""

CRITICAL = "critical"
ATTENTION = "attention"
OK = "ok"

LABELS = {CRITICAL: "Критический", ATTENTION: "Требует внимания", OK: "Без проблем"}


def compute(analysis: dict, score: float | None, has_next_step: bool) -> tuple[str, str]:
    """Возвращает (уровень, короткое объяснение «что не так»)."""
    risks = analysis.get("risks") or []
    high = [r for r in risks if r.get("level") == "high"]
    outcome = (analysis.get("outcome") or "").lower()
    refused = "отказ" in outcome
    agreements = analysis.get("agreements") or []

    if refused:
        reason = high[0]["text"] if high else "Клиент отказался"
        return CRITICAL, reason
    if high and not has_next_step:
        return CRITICAL, f"{high[0]['text']} и не назначен следующий шаг"
    if score is not None and score < 5:
        return CRITICAL, "Разговор проведён слабо: тренер нашёл грубые ошибки"
    if high:
        return ATTENTION, high[0]["text"]
    if not has_next_step:
        return ATTENTION, "Не назначен следующий шаг"
    if score is not None and score < 7:
        return ATTENTION, "Есть замечания по ведению разговора"
    if not agreements:
        return ATTENTION, "Нет явных договорённостей"
    return OK, ""
