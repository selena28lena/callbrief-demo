"""Контрольная проверка: верно ли расставлены роли «Менеджер/Клиент» в расшифровке.

Фикстура — реальная расшифровка звонка (имя клиента скрыто) в том виде, как её вернула
модель распознавания речи: метки там перепутаны. Эталон — 11 реплик, где говорящий
однозначен по смыслу разговора.

Запуск (нужен GEMINI_API_KEY в .env):
    python -m evals.speaker_roles            # три прогона исправления
    python -m evals.speaker_roles --runs 5
"""

import argparse
import time
from pathlib import Path

from app.services import pipeline

# mivino_call.txt — исходное распознавание, как его вернула модель (метки перепутаны).
# mivino_call_2.txt — второе распознавание той же записи после первой версии исправления:
# на нём видно, что эпизод с «роботом» размечается нестабильно.
FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("mivino_call*.txt"))

# (фрагмент реплики, кто её произнёс на самом деле). Менеджер — Даниил из компании «Мивино».
TRUTH = [
    ("это даниил компания мивино", "Менеджер"),
    ("что за компания", "Клиент"),
    ("с роботом разговариваю", "Клиент"),
    ("так, даниил, скажи", "Клиент"),
    ("крупнейши", "Менеджер"),
    ("по какому поводу ты звонишь", "Клиент"),
    ("хочу предложить вам партн", "Менеджер"),
    ("пассивный заработок", "Менеджер"),
    ("дружище, нет", "Клиент"),
    ("серой жидкости", "Клиент"),
    ("я не знаю ваш продукт", "Клиент"),
    ("не расслышал", "Менеджер"),
    ("я сейчас с роботом разговариваю", "Клиент"),
    ("меня даниил зовут", "Менеджер"),
]


def check(transcript: str) -> tuple[int, int, list[str]]:
    """Сколько эталонных реплик нашлось в расшифровке, сколько из них размечено верно и какие — нет.

    Разные распознавания записывают фразы чуть по-разному: реплику, которой в тексте нет,
    не считаем ни верной, ни ошибочной.
    """
    lines = transcript.lower().splitlines()
    found, wrong = 0, []
    for fragment, speaker in TRUTH:
        line = next((l for l in lines if fragment in l), None)
        if line is None:
            continue
        found += 1
        if ("менеджер:" in line) != (speaker == "Менеджер"):
            wrong.append(fragment)
    return found - len(wrong), found, wrong


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    total_before = total_after = total_found = 0
    for fixture in FIXTURES:
        source = fixture.read_text(encoding="utf-8")
        ok, found, wrong = check(source)
        print(f"=== {fixture.name}")
        print(f"ДО исправления:     {ok} из {found} верно")
        for fragment in wrong:
            print(f"    перепутано: «{fragment}»")
        for run in range(1, args.runs + 1):
            started = time.time()
            fixed, changed = pipeline.fix_speakers(source)
            ok_after, found_after, wrong_after = check(fixed)
            note = "  (модель недоступна — осталась исходная расшифровка)" if changed == 0 else ""
            print(f"ПОСЛЕ, прогон {run}:  {ok_after} из {found_after} верно · исправлено строк: {changed} · "
                  f"{time.time() - started:.0f} с{note}")
            for fragment in wrong_after:
                print(f"    перепутано: «{fragment}»")
            total_after += ok_after
            total_before += ok
            total_found += found_after
        print()

    print(f"Итого по всем прогонам: до — {total_before} из {total_found} верно, после — {total_after} из {total_found}")


if __name__ == "__main__":
    main()
