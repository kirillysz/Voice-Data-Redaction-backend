import logging
from dataclasses import dataclass
from app.core.config import settings

import numpy as np
if not hasattr(np, 'sctypes'):
    np.sctypes = {
        'int': [np.int8, np.int16, np.int32, np.int64],
        'uint': [np.uint8, np.uint16, np.uint32, np.uint64],
        'float': [np.float16, np.float32, np.float64],
        'complex': [np.complex64, np.complex128],
        'others': [bool, object, bytes, str, np.void],
    }

logger = logging.getLogger(__name__)

@dataclass
class WordTimestamp:
    word: str
    start_sec: float
    end_sec: float

_asr_model = None

def get_model(model_name: str):
    import torch
    global _asr_model
    if _asr_model is not None:
        return _asr_model

    try:
        import nemo.collections.asr as nemo_asr
        from omegaconf import open_dict
    except ImportError:
        raise RuntimeError("nemo_toolkit not found. Install with: pip install 'nemo_toolkit[asr]'")

    # model = nemo_asr.models.EncDecRNNTBPEModel.from_pretrained(model_name=model_name)
    model = nemo_asr.models.EncDecRNNTBPEModel.restore_from(restore_path=settings.LOCAL_ASR_MODEL_PATH)
    model.eval()

    if torch.cuda.is_available():
        model = model.cuda()

    decoding_cfg = model.cfg.decoding
    with open_dict(decoding_cfg):
        decoding_cfg.preserve_alignments = True
        decoding_cfg.compute_timestamps = True
    model.change_decoding_strategy(decoding_cfg)

    _asr_model = model  
    return _asr_model

def get_frame_shift(model) -> float:
    try:
        hop = float(model.cfg.preprocessor.window_stride)
    except (AttributeError, TypeError):
        hop = 0.01

    try:
        subsampling = int(model.cfg.encoder.subsampling_factor)
        return hop * subsampling
    except (AttributeError, TypeError):
        return hop * 8

def transcribe_with_timestamps(wav_path: str) -> list[WordTimestamp]:
    from app.core.config import settings
    
    if settings.USE_MOCK_ASR:
        return [
            WordTimestamp("hello", 0.0, 0.3),
            WordTimestamp("my", 0.35, 0.45),
            WordTimestamp("name", 0.5, 0.7),
            WordTimestamp("is", 0.75, 0.85),
            WordTimestamp("ivan", 0.9, 1.2),
            WordTimestamp("ivanov", 1.25, 1.7),
            WordTimestamp("phone", 2.0, 2.3),
            WordTimestamp("89991234567", 2.4, 3.5)
        ]

    model = get_model(settings.ASR_MODEL_NAME)
    frame_shift = get_frame_shift(model)

    hypotheses = model.transcribe([wav_path], return_hypotheses=True, batch_size=1)
    hyp = hypotheses[0]
    if isinstance(hyp, list):
        hyp = hyp[0]

    if hyp is None:
        return []

    word_timestamps = []

    for entry in hyp.timestep.get("word", []):
        word_timestamps.append(
            WordTimestamp(
                word=entry["word"],
                start_sec=round(entry["start_offset"] * frame_shift, 3),
                end_sec=round(entry["end_offset"] * frame_shift, 3),
            )
        )

    return word_timestamps
