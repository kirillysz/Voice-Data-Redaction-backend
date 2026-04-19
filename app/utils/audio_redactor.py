import logging
import shutil
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def mute_segments(audio_path: str, segments: list[tuple[float, float]], output_path: str):
    if not segments:
        shutil.copy2(audio_path, output_path)
        return

    audio = AudioSegment.from_wav(audio_path)

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

    for start, end in reversed(merged):
        s_ms, e_ms = int(start * 1000), int(end * 1000)
        duration = e_ms - s_ms
        if duration <= 0:
            continue
        silence = AudioSegment.silent(duration=duration, frame_rate=audio.frame_rate)
        audio = audio[:s_ms] + silence + audio[e_ms:]

    audio.export(output_path, format="wav")