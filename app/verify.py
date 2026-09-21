"""Проверка достоверности: есть ли цитата из ответа модели в исходном тексте."""

import math
import re
from difflib import SequenceMatcher

from .schemas import AnalyzeResponse, LLMResult, Verification

THRESHOLD = 0.85
MIN_FUZZY_WORDS = 3  # короткие цитаты проверяем только точным совпадением
STEM_LEN = 4
MIN_STEM_SHARE = 0.5
_NON_WORD = re.compile(r"[\W_]+")


def normalize(text: str) -> str:
    """Нижний регистр, ё→е, без пунктуации и лишних пробелов."""
    text = text.lower().replace("ё", "е")
    return _NON_WORD.sub(" ", text).strip()


def _match(quote_norm: str, source_norm: str, source_words: list[str], threshold: float) -> bool:
    if not quote_norm:
        return False
    # Точное вхождение по границам слов («да» не должно находиться в «когда»)
    if f" {quote_norm} " in f" {source_norm} ":
        return True

    q_words = quote_norm.split()
    n = len(q_words)
    if n < MIN_FUZZY_WORDS:
        return False

    # Быстрый отсев: окно должно содержать хотя бы половину «основ» слов цитаты
    # (первые 4 буквы — так «подготовлю» и «подготовим» считаются одним словом)
    q_stems = {w[:STEM_LEN] for w in q_words}
    prefix = [0]
    for w in source_words:
        prefix.append(prefix[-1] + (w[:STEM_LEN] in q_stems))
    need = math.ceil(n * MIN_STEM_SHARE)

    # Нечёткое совпадение: окно из n±20% слов скользит по тексту
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(quote_norm)  # seq2 кешируется, меняем только окно
    min_size = max(1, math.floor(n * 0.8))
    max_size = math.ceil(n * 1.2)
    for size in range(min_size, max_size + 1):
        for i in range(len(source_words) - size + 1):
            if prefix[i + size] - prefix[i] < need:
                continue
            matcher.set_seq1(" ".join(source_words[i:i + size]))
            if (
                matcher.real_quick_ratio() >= threshold
                and matcher.quick_ratio() >= threshold
                and matcher.ratio() >= threshold
            ):
                return True
    return False


def find_quote(quote: str, source: str, threshold: float = THRESHOLD) -> bool:
    source_norm = normalize(source)
    return _match(normalize(quote), source_norm, source_norm.split(), threshold)


def verify_result(result: LLMResult, source: str, model: str) -> AnalyzeResponse:
    """Добавляет каждому пункту verified и считает, сколько подтверждено."""
    source_norm = normalize(source)
    source_words = source_norm.split()
    data = result.model_dump()
    confirmed = total = 0
    for key in ("agreements", "next_steps", "risks", "recommendations"):
        for item in data[key]:
            item["verified"] = _match(normalize(item["quote"]), source_norm, source_words, THRESHOLD)
            total += 1
            confirmed += item["verified"]
    return AnalyzeResponse(
        **data, verification=Verification(confirmed=confirmed, total=total), model=model
    )
