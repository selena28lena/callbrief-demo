"""Регрессия: не ломает ли уточнение ролей звонки, где роли уже размечены верно.

Берём восемь разных разговоров из демо-набора (вымышленные данные). Правильная разметка
в них известна заранее, поэтому любая перепутанная метка — это ошибка исправления.
Дополнительно проверяем, что текст реплик не потерян и не переписан.

Запуск (нужен GEMINI_API_KEY в .env):
    python -m evals.speaker_regression
"""

import time

from app import speakers
from app.services import demo_data, pipeline

SCENARIOS = [
    demo_data.scenario_demo_agreed, demo_data.scenario_price_lost, demo_data.scenario_competitor,
    demo_data.scenario_no_next_step, demo_data.scenario_good_objection, demo_data.scenario_no_decision_maker,
    demo_data.scenario_no_budget, demo_data.scenario_not_needed,
]


def words(rows: list[dict]) -> str:
    """Весь текст разговора без меток: после исправления он должен совпасть слово в слово."""
    return " ".join(" ".join(r["text"] for r in rows).split())


def main() -> None:
    total_lines = total_ok = broken_text = 0
    for scenario in SCENARIOS:
        transcript = scenario("Колесо", "Виктор", "автосервис", "Иван Петров")[0]
        truth = speakers.parse(transcript)
        started = time.time()
        fixed_text, _ = pipeline.fix_speakers(transcript)
        fixed = speakers.parse(fixed_text)

        # Сверяем по тексту реплики: исправление могло разрезать строку, поэтому не по номеру
        by_text = {r["text"]: r["speaker"] for r in fixed}
        ok = sum(1 for r in truth if by_text.get(r["text"]) == r["speaker"])
        text_same = words(truth) == words(fixed)
        total_lines += len(truth)
        total_ok += ok
        broken_text += not text_same
        wrong = [r["text"][:50] for r in truth if by_text.get(r["text"]) != r["speaker"]]
        print(f"{scenario.__name__:28} {ok:2} из {len(truth):2} меток верно · "
              f"текст {'сохранён' if text_same else 'ИЗМЕНЁН'} · {time.time() - started:.0f} с")
        for line in wrong:
            print(f"    перепутано: «{line}»")

    print()
    print(f"Итого: {total_ok} из {total_lines} меток верно, текст изменён в {broken_text} разговорах из {len(SCENARIOS)}")


if __name__ == "__main__":
    main()
