from pydantic import BaseModel

class PDEntityResponse(BaseModel):
    type: str
    text: str
    start_char: int
    end_char: int
    start_sec: float
    end_sec: float


class RedactionResponse(BaseModel):
    status: str
    original_transcript: str | None = None
    redacted_transcript: str | None = None
    entities: list[PDEntityResponse] = []
    redacted_audio_url: str | None = None
    log: list[dict] = []