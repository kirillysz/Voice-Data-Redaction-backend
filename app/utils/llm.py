import json
import logging

from dataclasses import dataclass, field
from app.utils.asr import WordTimestamp
from app.core.config import settings

from ollama import AsyncClient

logger = logging.getLogger(__name__)

@dataclass
class EntityResult:
    type: str
    text: str
    start_char: int
    end_char: int
    start_sec: float
    end_sec: float

@dataclass
class LLMResult:
    original_transcript: str
    redacted_transcript: str
    entities: list[EntityResult] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)

PLACEHOLDERS = {
    "PERSON": "[ИМЯ]",
    "PHONE": "[ТЕЛЕФОН]",
    "EMAIL": "[EMAIL]",
    "ADDRESS": "[АДРЕС]",
    "INN": "[ИНН]",
    "SNILS": "[СНИЛС]",
    "PASPORT": "[ПАСПОРТ]"
}

SYSTEM_PROMPT = """\
Ты — система извлечения персональных данных (PII). Твоя задача — найти в тексте все сущности перечисленных типов и вернуть их в формате JSON.

Типы сущностей и правила обнаружения:

1. PERSON — имена, фамилии, отчества людей. Извлекай как полное имя (если есть), либо отдельно имя или фамилию. НЕ извлекай: местоимения, названия организаций, должности.

2. PHONE — номера телефонов. Поддерживаются:
   - Цифровая запись: +7(912)345-67-89, 8-912-345-67-89, 79123456789.
   - Словесная запись на русском языке: цифры от 0 до 9, десятки (десять, двадцать и т.д.), сотни (двести, триста, девятьсот и т.д.), составные числа («девяносто шесть», «двести шесть»). Примеры: «семь», «девятьсот девяносто шесть», «двести шесть», «двадцать пять», «ноль два».
   - Разделители: пробелы, запятые, точки, дефисы — игнорируются.
   - Алгоритм: найди последовательность слов-чисел (игнорируя предлоги/союзы между ними), переведи каждое слово в цифру (например, «семь» → 7, «девяносто шесть» → 96, «двести» → 200). Объедини все цифры в одну строку. Если длина строки 11 и она начинается с 7 или 8 — это российский номер. Замени начальную 8 на 7. Приведи к виду 11 цифр. Если длина другая — оставь как есть (возможно, городской номер).

3. EMAIL — адрес электронной почты. Приведи к нижнему регистру.

4. ADDRESS — любая географическая или адресная информация:
   - города (включая склонения: «Томске», «Москва», «в Томске», «из Томска»);
   - сёла, деревни, посёлки;
   - улицы, проспекты, переулки, бульвары;
   - номера домов, корпусов, квартир;
   - страна, область, район, индекс.
   Извлекай как непрерывный фрагмент (до знака препинания или пробела, если коротко).

5. INN — 10 или 12 цифр подряд.

6. SNILS — формат XXX-XXX-XXX XX или 11 цифр. Приведи к виду XXX-XXX-XXX XX.

7. PASPORT — серия и номер (обычно 4 и 6 цифр, разделённые пробелом/дефисом).

**Важно:** НЕ извлекай плейсхолдеры: [ИМЯ], [ТЕЛЕФОН], [EMAIL], [АДРЕС], [ИНН], [СНИЛС], [ПАСПОРТ]. Если пользователь написал их буквально — игнорируй.

Формат ответа — только валидный JSON без комментариев, без markdown-блоков:
{
  "entities": [
    {"type": "PERSON", "text": "Иван Иванов"},
    {"type": "PHONE", "text": "89991234567"}
  ]
}
Если сущностей нет: {"entities": []}

Примеры:

Вход: «Здравствуйте . Меня зовут [ИМЯ] . Мой номер телефона семь девятьсот девяносто шесть , двести шесть , двадцать пять , ноль два . Я живу в городе [АДРЕС] .»
Выход:
{
  "entities": [
    {"type": "PHONE", "text": "79962062502"}
  ]
}

Вход: «Здравствуйте. Меня зовут Алексей Смирнов. Я живу в городе Томске, на улице Ленина, 15.»
Выход:
{
  "entities": [
    {"type": "PERSON", "text": "Алексей Смирнов"},
    {"type": "ADDRESS", "text": "Томске"},
    {"type": "ADDRESS", "text": "улице Ленина, 15"}
  ]
}

Вход: «Москва, Кремль, дом 1. Телефон 8-495-123-45-67.»
Выход:
{
  "entities": [
    {"type": "ADDRESS", "text": "Москва"},
    {"type": "ADDRESS", "text": "Кремль, дом 1"},
    {"type": "PHONE", "text": "84951234567"}
  ]
}

Вход: «Позвони по номеру семь восемь девятьсот одиннадцать тридцать два ноль три.»
Выход:
{
  "entities": [
    {"type": "PHONE", "text": "789113203"}   // если 9 цифр, то без изменений
  ]
}

Вход: «Иван Петрович, ваш СНИЛС 123-456-789 01, ИНН 123456789012.»
Выход:
{
  "entities": [
    {"type": "PERSON", "text": "Иван Петрович"},
    {"type": "SNILS", "text": "123-456-789 01"},
    {"type": "INN", "text": "123456789012"}
  ]
}
"""

def get_placeholder(entity_type: str) -> str:
    return PLACEHOLDERS.get(entity_type.upper(), f"[{entity_type.upper()}]")

def map_timecodes(text: str, start_char: int, end_char: int, words: list[WordTimestamp]) -> tuple[float, float]:
    """
    Map character offsets in transcript to timestamps from ASR word list.
    """
    cursor = 0
    matched = []

    for w in words:
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

        w_start = cursor
        w_end = cursor + len(w.word)
        cursor = w_end

        if w_end > start_char and w_start < end_char:
            matched.append(w)

    if not matched:
        return 0.0, 0.0
    return matched[0].start_sec, matched[-1].end_sec

def apply_redaction(transcript: str, entities: list[EntityResult]) -> str:
    """
    Replace detected entities with placeholders (right-to-left to preserve offsets).
    """
    result = transcript
    for ent in sorted(entities, key=lambda e: e.start_char, reverse=True):
        result = result[:ent.start_char] + get_placeholder(ent.type) + result[ent.end_char:]
    return result

def _find_entity_offsets(transcript: str, entity_text: str) -> list[tuple[int, int]]:
    """Find all occurrences of entity_text in transcript (case-insensitive)."""
    results = []
    lower_t = transcript.lower()
    lower_e = entity_text.lower()
    start = 0
    while True:
        idx = lower_t.find(lower_e, start)
        if idx == -1:
            break
        results.append((idx, idx + len(entity_text)))
        start = idx + 1
    return results


async def redact_with_llm(transcript: str, words: list[WordTimestamp]) -> LLMResult:
    client = AsyncClient()

    try:
        response = await client.chat(
            model=settings.QWEN_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            options={
                "temperature": 0.0,
                "num_predict": 1024,
            },
        )

        raw_content = response.message.content.strip()

        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]

        parsed = json.loads(raw_content)
        raw_entities = parsed.get("entities", [])

    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        logger.error("LLM response parse error: %s", exc)
        return LLMResult(transcript, transcript, [], [])

    entities: list[EntityResult] = []
    seen_offsets: set[tuple[int, int]] = set()

    for item in raw_entities:
        etype = item.get("type", "UNKNOWN").upper()
        etext = item.get("text", "")
        if not etext:
            continue

        for start_char, end_char in _find_entity_offsets(transcript, etext):
            if (start_char, end_char) in seen_offsets:
                continue
            seen_offsets.add((start_char, end_char))

            start_sec, end_sec = map_timecodes(transcript, start_char, end_char, words)
            entities.append(EntityResult(
                type=etype,
                text=transcript[start_char:end_char],
                start_char=start_char,
                end_char=end_char,
                start_sec=start_sec,
                end_sec=end_sec,
            ))

    redacted = apply_redaction(transcript, entities)
    log = [
        {"type": e.type, "text": e.text, "replaced_with": get_placeholder(e.type)}
        for e in entities
    ]

    logger.info("LLM redaction: %d entities found", len(entities))
    return LLMResult(transcript, redacted, entities, log)