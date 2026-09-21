"""Тесты проверки цитат — без обращения к Gemini API."""

from app.schemas import Agreement, LLMResult, NextStep, Recommendation, Risk
from app.verify import find_quote, normalize, verify_result

SOURCE = """Менеджер: Отлично, договорились: демонстрация в четверг в одиннадцать утра, с вами и администратором.
Клиент: Хорошо, выгрузку подготовлю к четвергу. Ещё вопрос — всё ли в силе?
Менеджер: Коммерческое предложение пришлю до пятницы, учтём ёлочные игрушки."""


def test_normalize():
    assert normalize("Ёлка,  ДА!  — нет?\n«Ок»") == "елка да нет ок"


def test_exact_quote():
    assert find_quote("демонстрация в четверг в одиннадцать утра", SOURCE)


def test_quote_with_different_punctuation_and_case():
    assert find_quote("ДОГОВОРИЛИСЬ — демонстрация в четверг, в одиннадцать утра!", SOURCE)


def test_quote_with_e_instead_of_yo():
    assert find_quote("учтем елочные игрушки", SOURCE)


def test_invented_quote():
    assert not find_quote("Мы подпишем договор на год и оплатим всё сразу", SOURCE)


def test_similar_but_different_quote_is_rejected():
    assert not find_quote("демонстрация в пятницу в десять вечера без администратора", SOURCE)


def test_fuzzy_match_one_word_changed():
    # «подготовлю» → «подготовим»: модель слегка исказила слово, смысл тот же
    assert find_quote("Хорошо, выгрузку подготовим к четвергу", SOURCE)


def test_short_quote_matches_whole_words_only():
    assert not find_quote("да", "Когда будет готово?")


def test_empty_quote():
    assert not find_quote("", SOURCE)
    assert not find_quote("...", SOURCE)


def test_verify_result_marks_items_and_counts():
    result = LLMResult(
        summary="Договорились о демо.",
        outcome="встреча",
        crm_comment="Договорились о демонстрации продукта.",
        agreements=[Agreement(text="Демо", who="обе стороны", quote="демонстрация в четверг в одиннадцать утра")],
        next_steps=[NextStep(action="Выгрузка", owner="Клиент", deadline="к четвергу",
                             quote="выгрузку подготовлю к четвергу")],
        risks=[Risk(text="Выдумка", level="high", advice="Уточнить у клиента", quote="клиент уходит к конкуренту")],
        recommendations=[Recommendation(text="Подготовить КП", quote="Коммерческое предложение пришлю до пятницы")],
        open_questions=[],
    )
    resp = verify_result(result, SOURCE, model="test")
    assert resp.agreements[0].verified is True
    assert resp.next_steps[0].verified is True
    assert resp.risks[0].verified is False
    assert resp.recommendations[0].verified is True
    assert resp.verification.confirmed == 3
    assert resp.verification.total == 4
