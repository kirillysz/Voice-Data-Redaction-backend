import asyncio
import logging
import os
from pathlib import Path

from app.core.config import settings
from app.utils.audio import convert_to_wav16k
from app.utils.asr import transcribe_with_timestamps
from app.utils.audio_redactor import mute_segments

# Conditional import based on mock setting
if settings.USE_MOCK_LLM:
    from app.utils.mock_llm import redact_with_mock as redact_logic
else:
    from app.utils.llm import redact_with_llm as redact_logic

logger = logging.getLogger(__name__)

def process_audio_file(input_path: str, output_path: str) -> dict:
    Path(output_path).mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    wav_path = os.path.join(output_path, f"{stem}_processed.wav")

    logger.info(f"Processing audio: {input_path}")
    
    # 1. Prepare audio
    convert_to_wav16k(input_path, wav_path)

    # 2. Transcription
    words = transcribe_with_timestamps(wav_path)
    transcript = " ".join(w.word for w in words)

    # 3. Redaction logic (either mock or real template)
    llm_result = asyncio.run(redact_logic(transcript, words))
    print(llm_result)

    # 4. Audio muting
    redacted_wav_path = os.path.join(output_path, "redacted.wav")
    segments = [(e.start_sec, e.end_sec) for e in llm_result.entities]
    
    mute_segments(wav_path, segments, redacted_wav_path)

    return {
        "original_transcript": llm_result.original_transcript,
        "redacted_transcript": llm_result.redacted_transcript,
        "entities": [
            {
                "type": e.type, "text": e.text,
                "start_char": e.start_char, "end_char": e.end_char,
                "start_sec": e.start_sec, "end_sec": e.end_sec
            } for e in llm_result.entities
        ],
        "words": [{"word": w.word, "start_sec": w.start_sec, "end_sec": w.end_sec} for w in words],
        "redacted_audio_path": redacted_wav_path,
        "log": llm_result.log
    }