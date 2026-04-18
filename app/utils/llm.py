import logging
from dataclasses import dataclass, field
from app.utils.asr import WordTimestamp

logger = logging.getLogger(__name__)

# dis outta work, don't blame me if it's empty
# real llm magic coming soon (maybe)

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

def get_placeholder(entity_type: str) -> str:
    return PLACEHOLDERS.get(entity_type.upper(), f"[{entity_type.upper()}]")

def map_timecodes(text: str, start_char: int, end_char: int, words: list[WordTimestamp]) -> tuple[float, float]:
    """
    dis outta work for real, mapping chars to seconds
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

    if not matched: return 0.0, 0.0
    return matched[0].start_sec, matched[-1].end_sec

def apply_redaction(transcript: str, entities: list[EntityResult]) -> str:
    """
    replacing secrets with placeholders
    """
    result = transcript
    for ent in sorted(entities, key=lambda e: e.start_char, reverse=True):
        result = result[:ent.start_char] + get_placeholder(ent.type) + result[ent.end_char:]
    return result

async def redact_with_llm(transcript: str, words: list[WordTimestamp]) -> LLMResult:
    """
    TODO: implement real api call here
    for now this just returns empty
    """
    logger.warning("real llm redact_with_llm called but not implemented")
    return LLMResult(transcript, transcript, [], [])
