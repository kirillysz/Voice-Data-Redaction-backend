import time
import os

from app.utils.processor import process_audio_file
from app.utils.history import save_history_entry


def process_job(input_path: str, output_path: str, filename: str = "") -> dict:
    time.sleep(0.5)

    result = process_audio_file(
        input_path=input_path,
        output_path=output_path,
    )

    job_result = {
        "original_transcript": result.get("original_transcript"),
        "redacted_transcript":  result.get("redacted_transcript"),
        "entities":             result.get("entities", []),
        "words":                result.get("words", []),
        "redacted_audio_url":   result.get("redacted_audio_path"),
        "duration_sec":         result.get("duration_sec", 0.0),
        "log":                  result.get("log", []),
    }

    # Derive job_id from output_path (last path component equals job_id)
    job_id = os.path.basename(output_path.rstrip("/\\"))

    save_history_entry(
        job_id=job_id,
        filename=filename or os.path.basename(input_path),
        duration_sec=job_result["duration_sec"],
        entities=job_result["entities"],
        status="done",
    )

    return job_result