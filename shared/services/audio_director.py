"""Plan a small number of intentional SFX cues from semantic beats."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from shared.core.beat_timeline import BeatTimeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SFX_DIR = PROJECT_ROOT / "assets" / "sfx"
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}
ALIASES = {
    "warning": ("warning", "alert", "alarm"),
    "number": ("number", "pop", "click", "impact"),
    "reveal": ("reveal", "impact", "hit"),
    "turn": ("turn", "whoosh", "swoosh", "transition"),
}


@dataclass(frozen=True)
class SFXCue:
    timestamp: float
    asset_path: str
    cue_type: str
    gain: float
    reason: str
    beat_index: int

    def to_dict(self):
        return asdict(self)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_text = ascii_text.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _assets_by_name(sfx_dir: Path) -> list[Path]:
    if not sfx_dir.exists():
        return []
    return sorted(
        path for path in sfx_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _find_asset(files: Iterable[Path], cue_type: str, explicit: str = "") -> Path | None:
    files = list(files)
    explicit_key = _plain(explicit)
    if explicit_key and explicit_key not in {"none", "no", "khong"}:
        explicit_tokens = set(explicit_key.split())
        for path in files:
            if explicit_tokens & set(_plain(path.stem).split()):
                return path
    for alias in ALIASES.get(cue_type, (cue_type,)):
        for path in files:
            if alias in _plain(path.stem):
                return path
    return None


def plan_audio_cues(
    timeline: BeatTimeline,
    *,
    is_sensitive: bool = False,
    sfx_dir: str | os.PathLike[str] = DEFAULT_SFX_DIR,
    max_cues: int | None = None,
) -> list[SFXCue]:
    """Choose deterministic cues at turns, warnings, reveals, or key numbers."""
    if is_sensitive:
        return []
    limit = max_cues if max_cues is not None else (2 if timeline.total_duration <= 35 else 3)
    limit = max(0, min(3, int(limit)))
    files = _assets_by_name(Path(sfx_dir))
    if not files or limit == 0:
        return []

    cues: list[SFXCue] = []
    last_timestamp = -10.0
    for segment in timeline.segments:
        cue_type = ""
        reason = ""
        combined = f"{segment.on_screen_text} {segment.voice_over}"
        explicit = _plain(segment.sfx)
        if explicit and explicit not in {"none", "no", "khong"}:
            cue_type = "warning" if "warn" in explicit or "canh bao" in explicit else "reveal"
            reason = "SFX được chỉ định trong beat"
        elif segment.role == "turn":
            cue_type = "turn"
            reason = "beat chuyển biến"
        elif segment.role == "evidence" and re.search(r"\d", combined):
            cue_type = "number"
            reason = "beat nhấn con số"
        elif segment.role in {"hook", "payoff"} and re.search(r"\b(canh bao|bat ngo|he lo)\b", _plain(combined)):
            cue_type = "warning" if "canh bao" in _plain(combined) else "reveal"
            reason = "beat cảnh báo/reveal"
        if not cue_type or segment.start - last_timestamp < 3.0:
            continue
        asset = _find_asset(files, cue_type, segment.sfx)
        if not asset:
            continue
        cues.append(SFXCue(
            timestamp=max(0.0, segment.start),
            asset_path=str(asset),
            cue_type=cue_type,
            gain=0.14 if cue_type in {"turn", "number"} else 0.12,
            reason=reason,
            beat_index=segment.index,
        ))
        last_timestamp = segment.start
        if len(cues) >= limit:
            break
    return cues
