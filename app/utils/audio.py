import os
from pathlib import Path
from pydub import AudioSegment

def convert_to_wav16k(input_path: str, output_path: str | None = None) -> str:
    """
    Converts audio to WAV 16kHz Mono, required for the ASR model.
    """
    input_path = str(input_path)
    # Get extension for pydub's format parameter
    ext = Path(input_path).suffix.lower().lstrip(".")
    fmt = ext if ext else "wav"

    audio = AudioSegment.from_file(input_path, format=fmt)
    
    # Standardize to 16kHz Mono
    audio = audio.set_frame_rate(16000).set_channels(1)

    if not output_path:
        output_path = str(Path(input_path).with_suffix(".16k.wav"))

    audio.export(output_path, format="wav")
    return os.path.abspath(output_path)
