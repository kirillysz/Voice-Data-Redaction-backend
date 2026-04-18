from app.utils.processor import process_audio_file

def process_job(input_path: str, output_path: str):
    result = process_audio_file(
        input_path=input_path,
        output_path=output_path,
    )
    return {
        "original_transcript": result.get("original_transcript"),
        "redacted_transcript": result.get("redacted_transcript"),
        "entities": result.get("entities", []),  # уже список словарей
        "redacted_audio_url": result.get("redacted_audio_path"),
        "log": result.get("log", []),
    }