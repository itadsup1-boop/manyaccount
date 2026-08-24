"""Turn normalized content beats into a deterministic render timeline."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


ALLOWED_MOTIONS = {
    "static",
    "slow_push_in",
    "slow_pull_out",
    "pan_left",
    "pan_right",
}
ALLOWED_TRANSITIONS = {"cut", "fade"}
ROLE_WEIGHTS = {
    "hook": 2.2,
    "context": 2.8,
    "evidence": 3.8,
    "development": 3.5,
    "turn": 2.8,
    "payoff": 2.8,
    "close": 2.2,
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact_overlay_text(value: Any, fallback: Any = "", max_words: int = 7) -> str:
    """Create a short first-frame/beat headline without inventing new words."""
    primary = _text(value).strip(" .,:;!?-–—")
    fallback_text = _text(fallback).strip(" .,:;!?-–—")
    source = primary or fallback_text
    words = source.split()
    if len(words) < 3 and fallback_text and fallback_text != source:
        words = (source + " " + fallback_text).split()
    return " ".join(words[:max(3, int(max_words))]).strip(" .,:;!?-–—")


def _float(value: Any, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _allocate(weights: list[float], total: float, minimum: float = 0.45) -> list[float]:
    if not weights:
        return []
    total = max(0.1, float(total))
    if total <= minimum * len(weights):
        return [total / len(weights)] * len(weights)
    positive = [max(0.1, value) for value in weights]
    free = total - minimum * len(weights)
    weight_sum = sum(positive)
    return [minimum + free * value / weight_sum for value in positive]


@dataclass(frozen=True)
class BeatSegment:
    index: int
    role: str
    start: float
    end: float
    duration: float
    media_index: int
    voice_over: str = ""
    visual_query: str = ""
    on_screen_text: str = ""
    motion: str = "static"
    transition: str = "cut"
    sfx: str = ""
    must_show: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BeatTimeline:
    total_duration: float
    hook_duration: float
    first_frame_text: str
    segments: tuple[BeatSegment, ...]
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fallback_beats(media_count: int, hook_text: str) -> list[dict[str, Any]]:
    count = max(1, media_count)
    result = []
    for index in range(count):
        role = "hook" if index == 0 else "payoff" if index == count - 1 else "development"
        result.append({
            "role": role,
            "duration_hint": ROLE_WEIGHTS[role],
            "on_screen_text": compact_overlay_text(hook_text) if index == 0 else "",
            "motion": "slow_push_in" if index == 0 else "static",
            "transition": "cut",
        })
    return result


def plan_beat_timeline(
    beats: Sequence[Mapping[str, Any]] | None,
    *,
    total_duration: float,
    hook_duration: float = 0.0,
    media_count: int = 1,
    hook_text: str = "",
) -> BeatTimeline:
    """Allocate the real audio duration across semantic beats.

    The hook beat follows the real hook audio when available. Remaining beats
    are normalized from ``duration_hint``/role weights, so the video is never
    stretched to a hard-coded target duration.
    """
    total = max(0.1, float(total_duration or 0.0))
    media_count = max(1, int(media_count or 1))
    clean_beats = [dict(item) for item in (beats or []) if isinstance(item, Mapping)]
    used_fallback = not clean_beats
    if not clean_beats:
        clean_beats = _fallback_beats(media_count, hook_text)

    weights = []
    for item in clean_beats:
        role = _text(item.get("role")).lower() or "development"
        weights.append(_float(item.get("duration_hint"), ROLE_WEIGHTS.get(role, 3.0)))

    durations: list[float]
    real_hook = min(max(0.0, float(hook_duration or 0.0)), total)
    first_role = _text(clean_beats[0].get("role")).lower()
    if len(clean_beats) > 1 and first_role == "hook" and real_hook > 0:
        minimum_total = 0.45 * len(clean_beats)
        if total <= minimum_total:
            durations = [total / len(clean_beats)] * len(clean_beats)
        else:
            max_hook = total - 0.45 * (len(clean_beats) - 1)
            first_duration = min(max_hook, max(0.45, real_hook))
            durations = [first_duration] + _allocate(
                weights[1:],
                total - first_duration,
            )
    else:
        durations = _allocate(weights, total)

    # Remove floating-point drift from the final segment.
    if durations:
        durations[-1] += total - sum(durations)

    segments: list[BeatSegment] = []
    cursor = 0.0
    denominator = max(1, len(clean_beats) - 1)
    for index, (item, duration) in enumerate(zip(clean_beats, durations)):
        role = _text(item.get("role")).lower() or "development"
        motion = _text(item.get("motion")).lower()
        if motion not in ALLOWED_MOTIONS:
            motion = "slow_push_in" if index == 0 else "static"
        transition = _text(item.get("transition")).lower()
        if transition not in ALLOWED_TRANSITIONS:
            transition = "cut"
        must_show = item.get("must_show") or []
        if isinstance(must_show, str):
            must_show = [must_show]
        media_index = min(
            media_count - 1,
            round(index * (media_count - 1) / denominator),
        )
        end = total if index == len(clean_beats) - 1 else cursor + duration
        segments.append(BeatSegment(
            index=index,
            role=role,
            start=round(cursor, 3),
            end=round(end, 3),
            duration=round(max(0.05, end - cursor), 3),
            media_index=media_index,
            voice_over=_text(item.get("voice_over")),
            visual_query=_text(item.get("visual_query")),
            on_screen_text=compact_overlay_text(item.get("on_screen_text"), max_words=7),
            motion=motion,
            transition=transition,
            sfx=_text(item.get("sfx")),
            must_show=tuple(_text(value) for value in must_show if _text(value)),
        ))
        cursor = end

    first = segments[0]
    first_frame_text = compact_overlay_text(
        first.on_screen_text,
        hook_text or first.voice_over,
        max_words=7,
    )
    return BeatTimeline(
        total_duration=round(total, 3),
        hook_duration=round(real_hook, 3),
        first_frame_text=first_frame_text,
        segments=tuple(segments),
        used_fallback=used_fallback,
    )
