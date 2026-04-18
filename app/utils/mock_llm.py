import re
import logging
from dataclasses import dataclass
from app.utils.asr import WordTimestamp
from app.utils.llm import EntityResult, LLMResult, map_timecodes, apply_redaction, get_placeholder

logger = logging.getLogger(__name__)

async def redact_with_mock(transcript: str, words: list[WordTimestamp]) -> LLMResult:
    """
    Regex-based redaction for development/testing.
    """
    patterns = [
        ("PERSON", r"(ivan\s+ivanov|иван\s+иванов)"),
        ("PHONE", r"(\d{11}|8\d{10})"),
        ("EMAIL", r"[\w\.-]+@[\w\.-]+\.\w+")
    ]
    
    entities = []
    for etype, pattern in patterns:
        for m in re.finditer(pattern, transcript, re.IGNORECASE):
            s_sec, e_sec = map_timecodes(transcript, m.start(), m.end(), words)
            entities.append(EntityResult(
                type=etype,
                text=m.group(),
                start_char=m.start(),
                end_char=m.end(),
                start_sec=s_sec,
                end_sec=e_sec
            ))

    redacted = apply_redaction(transcript, entities)
    log = [{"type": e.type, "text": e.text, "replaced_with": get_placeholder(e.type)} for e in entities]

    return LLMResult(transcript, redacted, entities, log)
