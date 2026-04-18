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
    "ADDRESS": "[АДРЕС]"
}

SYSTEM_PROMPT = """\
Ты — система защиты персональных данных. Твоя задача — найти в тексте все персональные данные и вернуть их в формате JSON.

Ищи следующие типы сущностей:
- PERSON — имена, фамилии, отчества людей
- PHONE — номера телефонов в любом формате
- EMAIL — адреса электронной почты
- ADDRESS — физические адреса, улицы, города

Верни ТОЛЬКО валидный JSON без комментариев и markdown-блоков, в следующем формате:
{
  "entities": [
    {"type": "PERSON", "text": "Иван Иванов"},
    {"type": "PHONE", "text": "89991234567"}
  ]
}

Если персональных данных нет — верни {"entities": []}.
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