"""Уточнение ролей в расшифровке: кто говорит — менеджер или клиент.

Модель, которая расшифровывает звук, различает голоса по аудио и на телефонной записи
(один канал, похожая громкость) нередко путает их с середины разговора. Второй проход
смотрит уже на смысл реплик и возвращает только метки — текст не переписывается,
поэтому проверка цитат продолжает работать по исходным словам.
"""

import re

LINE = re.compile(r"^\[(?P<time>[0-9:]+)\]\s*(?P<speaker>Менеджер|Клиент):\s*(?P<text>.*)$")
OTHER = {"Менеджер": "Клиент", "Клиент": "Менеджер"}


def parse(transcript: str) -> list[dict]:
    """Разбирает расшифровку на строки. Строки без метки сохраняются как есть."""
    rows = []
    for raw in transcript.splitlines():
        m = LINE.match(raw.strip())
        if m:
            rows.append({"time": m["time"], "speaker": m["speaker"], "text": m["text"].strip()})
        elif raw.strip():
            rows.append({"time": None, "speaker": None, "text": raw.strip()})
    return rows


def numbered(rows: list[dict]) -> str:
    """Текст для модели: номер строки и реплика.

    Старые метки намеренно не показываем: увидев их, модель склонна просто переписать
    ошибку, а не определять говорящего по смыслу.
    """
    return "\n".join(f"{i}. {r['text']}" for i, r in enumerate(rows) if r["speaker"])


def apply(rows: list[dict], fixes: list[dict]) -> list[dict]:
    """Проставляет новые метки и разрезает строки, где слиплись реплики двух людей."""
    by_index = {f["index"]: f for f in fixes}
    out = []
    for i, row in enumerate(rows):
        fix = by_index.get(i)
        if not row["speaker"] or not fix:
            out.append(row)
            continue
        speaker = fix["speaker"]
        cut = (fix.get("second_speaker_starts_with") or "").strip()
        pos = row["text"].find(cut) if cut else -1
        if pos > 0:
            out.append({**row, "speaker": speaker, "text": row["text"][:pos].strip()})
            out.append({**row, "speaker": OTHER[speaker], "text": row["text"][pos:].strip()})
        else:
            out.append({**row, "speaker": speaker})
    return out


def render(rows: list[dict]) -> str:
    return "\n".join(
        f"[{r['time']}] {r['speaker']}: {r['text']}" if r["speaker"] else r["text"] for r in rows
    )


def changed_count(rows: list[dict], fixes: list[dict]) -> int:
    """Сколько строк исправлено: сменилась метка или строка разрезана надвое."""
    n = 0
    for f in fixes:
        i = f["index"]
        if 0 <= i < len(rows) and rows[i]["speaker"]:
            if f["speaker"] != rows[i]["speaker"] or (f.get("second_speaker_starts_with") or "").strip():
                n += 1
    return n
