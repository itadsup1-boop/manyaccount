"""Speech-to-text transcriber using Faster-Whisper for source video processing."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional

_WHISPER_MODEL_CACHE: dict[str, Any] = {}


def get_whisper_model(model_name: str = "base"):
    """Get or load cached Faster-Whisper model."""
    if model_name not in _WHISPER_MODEL_CACHE:
        from faster_whisper import WhisperModel

        print(f"   🤖 Loading Faster-Whisper model '{model_name}'...")
        _WHISPER_MODEL_CACHE[model_name] = WhisperModel(
            model_name, device="cpu", compute_type="float32"
        )
    return _WHISPER_MODEL_CACHE[model_name]


def extract_transcript_from_media(
    media_path: str,
    *,
    model_name: str = "base",
    language: str = "vi",
) -> str:
    """Extract spoken text transcript from a media file using Faster-Whisper.
    
    Returns cleaned plain text Vietnamese transcript.
    """
    if not media_path or not os.path.isfile(media_path):
        return ""

    try:
        t0 = time.time()
        model = get_whisper_model(model_name)
        segments, _info = model.transcribe(
            media_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        texts = []
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                texts.append(text)

        full_transcript = " ".join(texts).strip()
        full_transcript = re.sub(r"\s+", " ", full_transcript)
        elapsed = time.time() - t0
        if full_transcript:
            print(
                f"   🎙️ Whisper bóc tách xong ({elapsed:.1f}s): "
                f"{len(full_transcript.split())} từ thoại."
            )
        else:
            print(f"   ℹ️ Whisper không thấy lời thoại trong video ({elapsed:.1f}s).")
        return full_transcript
    except Exception as e:
        print(f"   ⚠️ Lỗi Whisper bóc tách thoại: {e}")
        return ""
