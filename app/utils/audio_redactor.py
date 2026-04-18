import logging
import math
import shutil
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def generate_beep(duration_ms: int, frame_rate: int, freq: int = 1000) -> AudioSegment:
    n_samples = int(frame_rate * duration_ms / 1000)
    samples = bytearray(n_samples * 2)
    amplitude = 32767 * 0.25 # -12dB approx
    
    for i in range(n_samples):
        val = int(amplitude * math.sin(2 * math.pi * freq * i / frame_rate))
        samples[2*i] = val & 0xFF
        samples[2*i+1] = (val >> 8) & 0xFF
        
    return AudioSegment(data=bytes(samples), sample_width=2, frame_rate=frame_rate, channels=1)

def mute_segments(audio_path: str, segments: list[tuple[float, float]], output_path: str):
    if not segments:
        shutil.copy2(audio_path, output_path)
        return

    audio = AudioSegment.from_wav(audio_path)
    
    # Merge segments to avoid redundant processing
    segments = sorted(segments, key=lambda x: x[0])
    merged = []
    if segments:
        curr_start, curr_end = segments[0]
        for s, e in segments[1:]:
            if s <= curr_end:
                curr_end = max(curr_end, e)
            else:
                merged.append((curr_start, curr_end))
                curr_start, curr_end = s, e
        merged.append((curr_start, curr_end))

    # Apply redaction from end to start
    for start, end in reversed(merged):
        s_ms, e_ms = int(start * 1000), int(end * 1000)
        duration = e_ms - s_ms
        if duration <= 0: continue
        
        beep = generate_beep(duration, audio.frame_rate)
        audio = audio[:s_ms] + beep + audio[e_ms:]

    audio.export(output_path, format="wav")
