"""Клиент Gemini: промпты, вызовы со структурированным ответом, обработка ошибок."""

import io
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from .schemas import LLMResult, ScoreResult, SpeakerFix

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gemini-3.5-flash"
TRANSCRIBE_MODEL = "gemini-3.5-flash-lite"   # расшифровка идёт на быстрой модели
RETRY_DELAY_SEC = 8
NETWORK_RETRY_DELAY_SEC = 2
TEMPERATURE = 0.15
REQUEST_TIMEOUT_MS = 120_000   # без таймаута оборванное соединение висит вечно

ANALYZE_SYSTEM = """Ты — аналитик отдела продаж. Тебе дают транскрипт разговора менеджера компании с клиентом.
Подготовь для руководителя достоверную выжимку разговора.

Строгие правила:
1. Извлекай ТОЛЬКО то, что явно сказано в разговоре. Ничего не додумывай, не делай выводов «между строк», не добавляй рекомендаций от себя.
2. Каждый пункт (договорённость, следующий шаг, риск) обязан содержать поле quote — ДОСЛОВНУЮ цитату из транскрипта: скопируй непрерывный фрагмент одной реплики символ в символ, без пересказа, без многоточий, без метки говорящего («Менеджер:», «Клиент:») и без меток времени вида [01:23]. Длина цитаты — примерно от 5 до 30 слов. Если подтверждающей цитаты нет — не добавляй пункт.
3. Договорённость — только то, на что стороны явно согласились. Слова «подумаем», «может быть», «наверное», «посмотрим», «надо обсудить» — это НЕ договорённость: отнеси такое к рискам или открытым вопросам.
4. Если договорённостей или следующего шага нет — верни пустой массив, а в open_questions напиши, чего не хватает (например: «Не согласована дата следующего контакта», «Не назван срок принятия решения»).
5. deadline — только если срок прямо назван в разговоре. Сохраняй формулировку как есть («в четверг», «до конца месяца»), не превращай в даты. Если срок не назван — null.
6. who: «компания» — обязательство менеджера или его компании, «клиент» — обязательство клиента, «обе стороны» — совместное действие (например, встреча).
7. owner: кто выполняет шаг — «Менеджер», «Клиент» или роль, названная в разговоре.
8. risks.level: high — угроза сорвать сделку (выбор конкурента, нет бюджета, нет решения, отказ); medium — сомнения, возражения, неопределённость; low — мелкие замечания. risks.text — конкретно, что именно и почему мешает сделке, а не общая формулировка. risks.advice — одно конкретное действие, которое менеджеру сделать с этим риском на следующем шаге.
9. summary — 2–3 нейтральных предложения о сути разговора и его итоге.
10. recommendations — 2–5 практических рекомендаций менеджеру или руководителю: на что обратить внимание и что сделать дальше. Каждая рекомендация опирается на конкретный момент разговора и содержит quote — дословную цитату этого момента по тем же правилам, что в пункте 2. Никаких общих советов без привязки к разговору; если опереться не на что — пустой массив.
11. contact_name — имя и/или должность собеседника со стороны клиента, если они прозвучали (например, «Руслан» или «Руслан, администратор»). Если не названы — null.
12. outcome — самый точный по смыслу итог разговора: «интерес», «отказ», «думает», «встреча» или «нет ответа».
13. crm_comment — развёрнутая заметка для карточки клиента в CRM, 5–10 предложений простым языком, без цитат и кавычек, по структуре: с кем и по какому поводу состоялся разговор; что клиент рассказал о своей ситуации и потребности; какие сомнения или возражения он озвучил; что предложил и ответил менеджер; о чём договорились (или почему не договорились); что мешает сделке; следующий шаг и срок, если он назван. Пиши только то, что реально прозвучало. Менеджер, открыв карточку через месяц, должен по этому тексту сразу вспомнить весь разговор.
14. Все тексты — на русском языке."""

SCORE_SYSTEM = """Ты — экспертный тренер отдела продаж (sales coach). Тебе дают транскрипт разговора менеджера с клиентом.
Оцени работу МЕНЕДЖЕРА (не клиента) по семи критериям, найди повторяющиеся ошибки и лучшие моменты.

Критерии — используй эти названия ровно, каждое ровно один раз, оценка от 1 до 10:
Приветствие, Выявление потребности, Квалификация клиента, Презентация, Работа с возражениями, Следующий шаг, Завершение звонка.

Правила:
1. Оценивай только то, что реально прозвучало. Если критерий не проявился (например, возражений не было) — оцени нейтрально (5–6) и поясни в comment, что проявить было нечего.
2. coach_items — конкретные ошибки менеджера: what_happened (что произошло, с опорой на реплику), why_problem (почему это мешает продаже), better_action (как сделать лучше), sample_phrase (готовая фраза для следующего раза). quote — дословная цитата реплики менеджера или клиента, к которой относится разбор, без метки говорящего и без меток времени. time_sec — секунда начала этой реплики, если в транскрипте есть метки времени вида [мм:сс] (переведи в секунды), иначе null. Не выдумывай ошибки — если их нет, верни пустой список.
3. best_moments — сильные моменты (score 8–10), где менеджер сработал хорошо: та же логика полей (score, time_sec, quote, why_good). Если таких моментов нет — пустой список.
4. strengths — названия критериев, где менеджер силён (score ≥ 8). blockers — названия критериев, которые реально мешали продаже (score ≤ 4). growth_area — одно название критерия с наибольшим потенциалом роста.
5. general_advice — 2–4 совета менеджеру на будущие звонки, которые следуют именно из этого разговора: что делать иначе в похожих ситуациях. Каждый совет — законченное практическое действие, а не лозунг вроде «работайте лучше».
6. Пиши деловым языком, без эмодзи. Все тексты на русском языке."""

SPEAKERS_SYSTEM = """Тебе дают расшифровку телефонного разговора менеджера по продажам с клиентом, по строкам: номер и реплика, без указания говорящего.
Определи, кто говорит в каждой строке, по СМЫСЛУ реплик и ходу разговора.

Порядок работы:
1. Сначала найди, как представился менеджер (имя) и от какой компании он звонит, — запиши в manager_name и company.
2. Дальше это опора для каждой строки: кто называет себя этим именем («меня Даниил зовут», «это Даниил, компания…») или говорит «мы производим», «наша компания», «я вам предлагаю» — это менеджер. Кто обращается к этому человеку по имени («Даниил, скажи…») или спрашивает, кто звонит и зачем, — это клиент.
3. Проверь каждую строку по смыслу отдельно, не опираясь на соседние: особенно короткие реплики и места, где кто-то переспрашивает или не расслышал.

Как отличить:
- Менеджер — сотрудник компании, который звонит сам: представляется от имени компании, называет своё имя, рассказывает о продукте, делает предложение, называет цены и условия, предлагает созвон или встречу, уговаривает.
- Клиент — тот, кому позвонили: отвечает на звонок, спрашивает «что за компания», «по какому поводу звоните», сомневается, возражает, отказывается.
- Если кто-то обращается к собеседнику по имени, которое менеджер назвал при знакомстве, — это говорит клиент.
- Реплики обычно чередуются, но один человек может сказать несколько строк подряд.

Если в одной строке слиплись реплики двух людей (например, вопрос и сразу ответ на него), укажи speaker для начала строки, а в second_speaker_starts_with — дословно первые 3–6 слов второго человека, точно как в тексте.

Верни запись для КАЖДОЙ строки входного списка, с её номером. Текст реплик не меняй и не пересказывай."""


class AppError(Exception):
    """Ошибка с понятным пользователю сообщением и HTTP-статусом."""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _load_env() -> None:
    # override=True: подхватываем правки .env без перезапуска сервера
    load_dotenv(BASE_DIR / ".env", override=True)


def get_api_key() -> str:
    _load_env()
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_model() -> str:
    _load_env()
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def get_transcribe_model() -> str:
    """Для расшифровки берём самую быструю модель: качество речи от неё не страдает."""
    _load_env()
    return os.getenv("GEMINI_TRANSCRIBE_MODEL", "").strip() or TRANSCRIBE_MODEL


def _client() -> tuple[genai.Client, str]:
    key = get_api_key()
    if not key:
        raise AppError(
            "no_key",
            "Не найден ключ Gemini API. Получите бесплатный ключ на aistudio.google.com/apikey "
            "и впишите его в файл .env: GEMINI_API_KEY=ваш_ключ",
            status=503,
        )
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    ), get_model()


def _map_api_error(e: errors.APIError, model: str) -> AppError:
    code = getattr(e, "code", None) or 0
    status = str(getattr(e, "status", "") or "").upper()
    msg = f"{getattr(e, 'message', '') or ''} {e}".lower()

    if "location" in msg and "not supported" in msg:
        return AppError("region", "Gemini недоступен в вашем регионе, включите VPN.", status=451)
    if code == 429 or "RESOURCE_EXHAUSTED" in status:
        text = "Лимит бесплатного тарифа, попробуйте через минуту."
        if "limit: 0" in msg:
            text += (f" Похоже, у модели {model} нет бесплатной квоты для вашего ключа — "
                     "смените GEMINI_MODEL в .env (например, на gemini-flash-latest).")
        return AppError("rate_limit", text, status=429)
    if "api key" in msg or "api_key" in msg or code in (401, 403):
        return AppError("bad_key", "Ключ Gemini API недействителен. Проверьте GEMINI_API_KEY в .env.", status=401)
    if code == 404:
        return AppError("bad_model", f"Модель «{model}» не найдена. Проверьте GEMINI_MODEL в .env.", status=400)
    if code >= 500:
        return AppError("unavailable", "Сервис Gemini временно недоступен, попробуйте чуть позже.", status=503)
    return AppError("api_error", f"Ошибка Gemini API ({code}): {getattr(e, 'message', '') or e}", status=502)


def _gen_config(model: str, thinking_level: str = "low", **kwargs) -> types.GenerateContentConfig:
    """Общие настройки: минимум «размышлений» (быстрее ответ, меньше расход квоты), без AFC."""
    if model.startswith("gemini-2"):
        thinking = types.ThinkingConfig(thinking_budget=0)
    else:
        thinking = types.ThinkingConfig(thinking_level=thinking_level)
    return types.GenerateContentConfig(
        thinking_config=thinking,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        **kwargs,
    )


def _call(fn, model: str):
    """Вызов API с одной повторной попыткой при лимите (429), перегрузке (5xx) или обрыве сети."""
    for attempt in (1, 2):
        try:
            return fn()
        except errors.APIError as e:
            err = _map_api_error(e, model)
            if attempt == 1 and err.code in ("rate_limit", "unavailable"):
                time.sleep(RETRY_DELAY_SEC)
                continue
            raise err from e
        except httpx.HTTPError as e:
            if attempt == 1:
                time.sleep(NETWORK_RETRY_DELAY_SEC)
                continue
            raise AppError(
                "network",
                "Не удалось подключиться к серверам Google. Скорее всего, Gemini недоступен "
                "в вашем регионе — включите VPN и попробуйте снова. Если VPN включён, "
                "проверьте подключение к интернету.",
                status=503,
            ) from e


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _parse_model(resp, model_cls):
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, model_cls):
        return parsed
    try:
        raw = resp.text
    except Exception:
        raw = None
    if not raw:
        raise AppError(
            "bad_response",
            "Модель вернула пустой ответ (возможно, сработал фильтр безопасности). Попробуйте ещё раз.",
        )
    try:
        return model_cls.model_validate_json(_strip_fences(raw))
    except (ValidationError, json.JSONDecodeError) as e:
        raise AppError(
            "bad_response", "Модель вернула ответ в неожиданном формате. Попробуйте ещё раз."
        ) from e


# Коды ошибок, при которых есть смысл попробовать другую модель: перегрузка, лимит, модель снята
FALLBACK_CODES = ("unavailable", "rate_limit", "bad_model")


def _models_chain() -> list[str]:
    """Основная модель, а при её перегрузке — быстрая: Google периодически отвечает 503 «high demand»."""
    chain = [get_model()]
    if get_transcribe_model() not in chain:
        chain.append(get_transcribe_model())
    return chain


def _structured(system: str, schema, text: str, thinking_level: str = "low"):
    """Структурированный ответ модели с переходом на запасную при перегрузке."""
    client, _ = _client()
    contents = f"Транскрипт разговора:\n\n{text}"
    last_error: AppError | None = None
    for model in _models_chain():
        config = _gen_config(
            model,
            thinking_level=thinking_level,
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=TEMPERATURE,
        )
        try:
            resp = _call(
                lambda: client.models.generate_content(model=model, contents=contents, config=config), model
            )
            return _parse_model(resp, schema), model
        except AppError as e:
            if e.code not in FALLBACK_CODES:
                raise
            last_error = e
    raise last_error


def analyze(text: str) -> tuple[LLMResult, str]:
    return _structured(ANALYZE_SYSTEM, LLMResult, text)


def fix_speakers(numbered_lines: str) -> tuple[SpeakerFix, str]:
    """Второй проход по расшифровке: метки «Менеджер/Клиент» по смыслу, а не по голосу."""
    # задача на рассуждение по ходу разговора — даём модели подумать
    return _structured(SPEAKERS_SYSTEM, SpeakerFix, numbered_lines, thinking_level="medium")


def score(text: str) -> tuple[ScoreResult, str]:
    """Второй вызов: оценка менеджера по критериям, разбор ошибок и лучшие моменты."""
    # разбор по фиксированным критериям — «размышления» тут не нужны
    return _structured(SCORE_SYSTEM, ScoreResult, text, thinking_level="minimal")


# --- Расшифровка аудио ------------------------------------------------------

INLINE_LIMIT_BYTES = 20 * 1024 * 1024  # больше — через Files API
UPLOAD_POLL_SEC = 2
UPLOAD_TIMEOUT_SEC = 180

TRANSCRIBE_PROMPT = """Дословно расшифруй эту аудиозапись разговора менеджера с клиентом на русском языке.

Формат ответа — строго построчно:
[мм:сс] Менеджер: текст реплики
[мм:сс] Клиент: текст реплики

Обязательные правила:
- КАЖДАЯ строка начинается с метки времени в квадратных скобках и роли говорящего с двоеточием. Строк без роли быть не должно.
- Одна реплика — одна строка. Если человек говорит долго, всё равно пиши одной строкой.
- Менеджер — тот, кто звонит и продаёт; клиент — тот, кому звонят.
- Записывай слова дословно, ничего не сокращай и не пересказывай.
- Неразборчивое помечай [неразборчиво].
- Выведи только строки расшифровки, без заголовков и комментариев."""


def _upload_audio(client: genai.Client, data: bytes, mime_type: str, filename: str, model: str):
    uploaded = _call(
        lambda: client.files.upload(
            file=io.BytesIO(data),
            config=types.UploadFileConfig(mime_type=mime_type, display_name=filename[:100]),
        ),
        model,
    )
    deadline = time.monotonic() + UPLOAD_TIMEOUT_SEC
    while uploaded.state == types.FileState.PROCESSING:
        if time.monotonic() > deadline:
            raise AppError("upload_timeout", "Gemini слишком долго обрабатывает файл. Попробуйте запись покороче.", 504)
        time.sleep(UPLOAD_POLL_SEC)
        name = uploaded.name
        uploaded = _call(lambda: client.files.get(name=name), model)
    if uploaded.state == types.FileState.FAILED:
        raise AppError("upload_failed", "Gemini не смог обработать аудиофайл. Проверьте, что файл не повреждён.")
    return uploaded


def transcribe(data: bytes, mime_type: str, filename: str, on_chunk=None) -> tuple[str, str]:
    """Расшифровка с запасной моделью.

    Быстрая модель иногда обрывает соединение; в этом случае молча переходим на основную,
    чтобы менеджер не ждал впустую.
    """
    models = [get_transcribe_model()]
    if get_model() not in models:
        models.append(get_model())

    last_error: AppError | None = None
    for model in models:
        try:
            return _transcribe_with(model, data, mime_type, filename, on_chunk)
        except AppError as e:
            if e.code not in ("network", "unavailable", "rate_limit", "bad_model", "bad_response"):
                raise
            last_error = e
            if e.code == "network":
                # Соединение рвётся на передаче файла: вторая модель пойдёт тем же каналом
                break
    if last_error and last_error.code == "network":
        raise AppError(
            "audio_network",
            "Не удалось передать запись в Gemini: соединение обрывается на загрузке файла. "
            "Чаще всего это VPN — он пропускает текст, но режет передачу больших файлов. "
            "Переключите сервер VPN и попробуйте снова. Либо вставьте текст разговора вручную.",
            status=503,
        )
    raise last_error


def _transcribe_with(model: str, data: bytes, mime_type: str, filename: str, on_chunk=None) -> tuple[str, str]:
    client, _ = _client()
    config = _gen_config(model, thinking_level="minimal", temperature=0)

    def generate(audio_part):
        if on_chunk is None:
            return _call(
                lambda: client.models.generate_content(
                    model=model, contents=[TRANSCRIBE_PROMPT, audio_part], config=config
                ),
                model,
            )

        def stream():
            parts: list[str] = []
            for event in client.models.generate_content_stream(
                model=model, contents=[TRANSCRIBE_PROMPT, audio_part], config=config
            ):
                piece = getattr(event, "text", None)
                if piece:
                    parts.append(piece)
                    on_chunk("".join(parts))
            return "".join(parts)

        return _call(stream, model)

    if len(data) <= INLINE_LIMIT_BYTES:
        resp = generate(types.Part.from_bytes(data=data, mime_type=mime_type))
    else:
        uploaded = _upload_audio(client, data, mime_type, filename, model)
        try:
            resp = generate(uploaded)
        finally:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass  # файл всё равно удалится сам через 48 часов

    try:
        text = (resp if isinstance(resp, str) else resp.text or "").strip()
    except Exception:
        text = ""
    if not text:
        raise AppError("bad_response", "Не удалось распознать речь в записи. Проверьте файл и попробуйте снова.")
    return _strip_fences(text), model
