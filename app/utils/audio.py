import os
import subprocess
from pathlib import Path

def convert_to_wav16k(input_path: str, output_path: str | None = None) -> str:
    input_path = str(input_path)
    if not output_path:
        output_path = str(Path(input_path).with_suffix(".16k.wav"))
    
    subprocess.run([
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        output_path
    ], check=True)
    
    return os.path.abspath(output_path)