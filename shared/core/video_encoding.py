"""Deterministic color grading and FFmpeg output presets for vertical video."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Mapping


FINAL_VIDEO_ARGS = [
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "19",
    "-pix_fmt", "yuv420p",
    "-profile:v", "high",
    "-level:v", "4.1",
    "-r", "30",
    "-fps_mode", "cfr",
    "-g", "60",
    "-keyint_min", "60",
    "-movflags", "+faststart",
]

FINAL_AUDIO_ARGS = [
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
]

# Strip source tags instead of pretending that another editing application
# produced the file. FFmpeg may still write its truthful muxer/codec tag.
CLEAN_METADATA_ARGS = ["-map_metadata", "-1", "-map_chapters", "-1"]

# TikTok Remix must materialize beat segments before concatenation. These
# intermediates are lossless video + lossless audio; only the final MP4 is lossy.
INTERMEDIATE_VIDEO_ARGS = [
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "0",
    "-pix_fmt", "yuv420p",
    "-r", "30",
    "-fps_mode", "cfr",
    "-g", "60",
    "-keyint_min", "60",
]

INTERMEDIATE_AUDIO_ARGS = [
    "-c:a", "flac",
    "-ar", "48000",
    "-ac", "2",
]


@dataclass(frozen=True)
class ColorGrade:
    name: str
    contrast: float
    saturation: float
    brightness: float
    sharpen: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


COLOR_PRESETS = {
    "clean_news": ColorGrade("clean_news", 1.02, 1.03, 0.0, 0.20),
    "serious_news": ColorGrade("serious_news", 1.01, 0.98, -0.01, 0.12),
    "warm_positive": ColorGrade("warm_positive", 1.01, 1.06, 0.01, 0.15),
    "sports_energy": ColorGrade("sports_energy", 1.03, 1.08, 0.0, 0.25),
    "entertainment_pop": ColorGrade("entertainment_pop", 1.02, 1.08, 0.005, 0.18),
    "sensitive_neutral": ColorGrade("sensitive_neutral", 1.0, 0.98, 0.0, 0.08),
}

COLOR_LIMITS = {
    "contrast": (0.94, 1.08),
    "saturation": (0.90, 1.12),
    "brightness": (-0.04, 0.04),
    "sharpen": (0.0, 0.35),
}


def _plain(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_text = ascii_text.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def _clamp(value: Any, key: str, fallback: float) -> float:
    low, high = COLOR_LIMITS[key]
    try:
        return round(max(low, min(high, float(value))), 3)
    except (TypeError, ValueError):
        return fallback


def _style_for_channel(channel_id: str) -> dict[str, Any]:
    if not channel_id:
        return {}
    try:
        from shared.core.prompt_builder import get_video_style

        style = get_video_style(channel_id)
        return dict(style) if isinstance(style, Mapping) else {}
    except Exception:
        return {}


def resolve_color_grade(
    channel_id: str = "",
    *,
    tone: str = "",
    is_sensitive: bool = False,
    video_style: Mapping[str, Any] | None = None,
) -> ColorGrade:
    """Resolve one bounded, deterministic color grade for the whole video."""
    style = dict(video_style) if isinstance(video_style, Mapping) else _style_for_channel(channel_id)
    color_block = style.get("color_preset", {})
    color_values = dict(color_block) if isinstance(color_block, Mapping) else {}

    requested = style.get("grading_preset") or color_values.get("name")
    if isinstance(color_block, str):
        requested = color_block

    tone_key = _plain(tone)
    if is_sensitive:
        preset_name = "sensitive_neutral"
    elif _plain(requested) in COLOR_PRESETS:
        preset_name = _plain(requested)
    elif tone_key in {"tich_cuc", "vui_ve", "positive"}:
        preset_name = "warm_positive"
    elif tone_key in {"nghiem_trong", "canh_bao", "serious", "warning"}:
        preset_name = "serious_news"
    else:
        preset_name = "clean_news"

    base = COLOR_PRESETS[preset_name]
    overrides = {} if is_sensitive else {**color_values, **style}
    return ColorGrade(
        name=preset_name,
        contrast=_clamp(overrides.get("contrast"), "contrast", base.contrast),
        saturation=_clamp(overrides.get("saturation"), "saturation", base.saturation),
        brightness=_clamp(overrides.get("brightness"), "brightness", base.brightness),
        sharpen=_clamp(overrides.get("sharpen"), "sharpen", base.sharpen),
    )


def build_color_filter(grade: ColorGrade) -> str:
    """Return an FFmpeg filter chain with only bounded editorial adjustments."""
    chain = (
        f"eq=contrast={grade.contrast:.3f}:"
        f"saturation={grade.saturation:.3f}:"
        f"brightness={grade.brightness:.3f}"
    )
    if grade.sharpen > 0:
        chain += (
            ",unsharp=luma_msize_x=5:luma_msize_y=5:"
            f"luma_amount={grade.sharpen:.3f}"
        )
    return chain


def final_output_args() -> list[str]:
    return [*FINAL_VIDEO_ARGS, *FINAL_AUDIO_ARGS, *CLEAN_METADATA_ARGS]


def intermediate_output_args() -> list[str]:
    return [*INTERMEDIATE_VIDEO_ARGS, *INTERMEDIATE_AUDIO_ARGS, *CLEAN_METADATA_ARGS]
