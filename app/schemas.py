"""Pydantic-модели: схема ответа модели (для response_schema) и ответы API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Who = Literal["клиент", "компания", "обе стороны"]
Level = Literal["high", "medium", "low"]


# --- Схема, которую заполняет Gemini --------------------------------------

class Agreement(BaseModel):
    text: str = Field(description="Суть договорённости, кратко")
    who: Who = Field(description="Чьё обязательство: клиент, компания или обе стороны")
    quote: str = Field(description="Дословная цитата из транскрипта")


class NextStep(BaseModel):
    action: str = Field(description="Что нужно сделать")
    owner: str = Field(description="Кто делает, как назван в разговоре")
    deadline: Optional[str] = Field(
        default=None, description="Срок, только если он назван, в исходной формулировке; иначе null"
    )
    quote: str = Field(description="Дословная цитата из транскрипта")


class Risk(BaseModel):
    text: str = Field(description="В чём риск: конкретно, что и почему может сорвать сделку")
    level: Level = Field(description="high, medium или low")
    advice: str = Field(description="Что менеджеру сделать с этим риском — одно конкретное действие")
    quote: str = Field(description="Дословная цитата из транскрипта")


class Recommendation(BaseModel):
    text: str = Field(description="Практическая рекомендация менеджеру или руководителю")
    quote: str = Field(description="Дословная цитата момента разговора, на котором основана рекомендация")


Outcome = Literal["интерес", "отказ", "думает", "встреча", "нет ответа"]


class LLMResult(BaseModel):
    summary: str = Field(description="2-3 предложения о сути и итоге разговора")
    contact_name: Optional[str] = Field(default=None, description="Имя и/или должность собеседника со стороны клиента, если названы")
    outcome: Outcome = Field(description="Короткий итог разговора")
    crm_comment: str = Field(description="Развёрнутая заметка для карточки клиента в CRM: 5-10 предложений без цитат")
    agreements: list[Agreement]
    next_steps: list[NextStep]
    risks: list[Risk]
    recommendations: list[Recommendation]
    open_questions: list[str]


# --- Схема оценки менеджера (второй вызов модели) --------------------------

Criterion = Literal[
    "Приветствие", "Выявление потребности", "Квалификация клиента",
    "Презентация", "Работа с возражениями", "Следующий шаг", "Завершение звонка",
]


class ScoreCriterion(BaseModel):
    name: Criterion
    score: int = Field(ge=1, le=10)
    comment: str = Field(description="Короткое пояснение оценки")


class CoachItem(BaseModel):
    skill: str = Field(description="Навык, к которому относится ошибка")
    time_sec: Optional[float] = Field(default=None, description="Секунда разговора, если в транскрипте есть метки времени")
    what_happened: str
    why_problem: str
    better_action: str
    sample_phrase: Optional[str] = None
    quote: str = Field(description="Дословная цитата момента, к которому относится разбор")


class BestMoment(BaseModel):
    skill: str
    score: int = Field(ge=1, le=10)
    time_sec: Optional[float] = None
    quote: str
    why_good: str


class ScoreResult(BaseModel):
    criteria: list[ScoreCriterion]
    strengths: list[str] = Field(description="Названия критериев, где менеджер силён")
    blockers: list[str] = Field(description="Названия критериев, которые реально мешали продаже")
    growth_area: str = Field(description="Название критерия с наибольшим потенциалом роста")
    general_advice: list[str] = Field(description="2-4 совета менеджеру на будущие звонки, следующие из этого разговора")
    coach_items: list[CoachItem]
    best_moments: list[BestMoment]


# --- Ответы API -------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    text: str = ""


class VerifiedAgreement(Agreement):
    verified: bool


class VerifiedNextStep(NextStep):
    verified: bool


class VerifiedRisk(Risk):
    verified: bool



class VerifiedRecommendation(Recommendation):
    verified: bool


class Verification(BaseModel):
    confirmed: int
    total: int


class AnalyzeResponse(BaseModel):
    summary: str
    contact_name: Optional[str] = None
    outcome: Outcome
    crm_comment: str
    agreements: list[VerifiedAgreement]
    next_steps: list[VerifiedNextStep]
    risks: list[VerifiedRisk]
    recommendations: list[VerifiedRecommendation]
    open_questions: list[str]
    verification: Verification
    model: str


class TranscribeResponse(BaseModel):
    text: str
    model: str


# --- Уточнение ролей в расшифровке -----------------------------------------

class SpeakerLabel(BaseModel):
    index: int = Field(description="Номер строки из входного списка")
    speaker: Literal["Менеджер", "Клиент"] = Field(description="Кто на самом деле говорит (или начинает строку)")
    second_speaker_starts_with: Optional[str] = Field(
        default=None,
        description="Если в строке слиплись реплики двух людей — первые 3-6 слов второго, дословно; иначе null",
    )


class SpeakerFix(BaseModel):
    # Сначала модель фиксирует, кто менеджер: дальше метки расставляются от этой опоры
    manager_name: Optional[str] = Field(default=None, description="Как представился менеджер (имя), если прозвучало")
    company: Optional[str] = Field(default=None, description="Компания, от имени которой звонит менеджер")
    lines: list[SpeakerLabel]
