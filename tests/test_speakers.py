"""Разметка ролей: разбор, перестановка меток и разрезание слипшихся реплик. Без обращения к API."""

from app import speakers

TRANSCRIPT = """[00:28] Менеджер: С роботом разговариваю.
[00:31] Менеджер: А, простите, не расслышал. Ещё раз можно?
[00:33] Клиент: Я сейчас с роботом разговариваю или с Нет, нет, конечно не робот, меня Даниил зовут."""


def test_parse_keeps_time_speaker_and_text():
    rows = speakers.parse(TRANSCRIPT)
    assert rows[0] == {"time": "00:28", "speaker": "Менеджер", "text": "С роботом разговариваю."}
    assert len(rows) == 3


def test_numbered_hides_old_labels():
    # старые метки модели не показываем, иначе она их просто копирует
    text = speakers.numbered(speakers.parse(TRANSCRIPT))
    assert "Менеджер" not in text and "Клиент" not in text
    assert text.startswith("0. С роботом разговариваю.")


def test_apply_relabels_and_splits_merged_line():
    rows = speakers.parse(TRANSCRIPT)
    fixes = [
        {"index": 0, "speaker": "Клиент"},
        {"index": 1, "speaker": "Менеджер"},
        {"index": 2, "speaker": "Клиент", "second_speaker_starts_with": "Нет, нет, конечно"},
    ]
    out = speakers.render(speakers.apply(rows, fixes)).splitlines()
    assert out == [
        "[00:28] Клиент: С роботом разговариваю.",
        "[00:31] Менеджер: А, простите, не расслышал. Ещё раз можно?",
        "[00:33] Клиент: Я сейчас с роботом разговариваю или с",
        "[00:33] Менеджер: Нет, нет, конечно не робот, меня Даниил зовут.",
    ]
    assert speakers.changed_count(rows, fixes) == 2


def test_apply_ignores_split_text_that_is_not_in_line():
    # модель ошиблась с цитатой второго говорящего — строку не режем, текст не теряем
    rows = speakers.parse(TRANSCRIPT)
    out = speakers.apply(rows, [{"index": 2, "speaker": "Клиент", "second_speaker_starts_with": "такого нет"}])
    assert out[2]["text"] == rows[2]["text"]


def test_missing_fix_keeps_original_label():
    rows = speakers.parse(TRANSCRIPT)
    out = speakers.apply(rows, [{"index": 0, "speaker": "Клиент"}])
    assert [r["speaker"] for r in out] == ["Клиент", "Менеджер", "Клиент"]
