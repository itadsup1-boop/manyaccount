"""Technical and editorial pre-upload quality gate for rendered videos."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from shared.core.safe_zone import validate_ass_file, validate_element_box
from shared.core.ffmpeg_utils import ffmpeg_command, ffprobe_command


@dataclass(frozen=True)
class VideoQAResult:
    container_valid: bool
    video_codec: str
    resolution: str
    aspect_ratio: str
    pixel_format: str
    fps: float
    audio_codec: str
    audio_sample_rate: int
    audio_channels: int
    decode_ok: bool
    safe_zone_ok: bool
    black_frame_ok: bool
    freeze_frame_ok: bool
    silence_ok: bool
    loudness_ok: bool
    watermark_ok: bool
    passed: bool
    blocking_errors: tuple[str, ...]
    warnings: tuple[str, ...]
    duration: float = 0.0
    integrated_lufs: float | None = None
    max_black_seconds: float = 0.0
    max_freeze_seconds: float = 0.0
    max_silence_seconds: float = 0.0

    @property
    def error_code(self) -> str:
        return self.blocking_errors[0] if self.blocking_errors else ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rate(value: Any) -> float:
    text = str(value or "0")
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / float(denominator or 1)
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _max_metric(log: str, name: str) -> float:
    values = re.findall(rf"{re.escape(name)}\s*:\s*([0-9.]+)", log or "")
    return max((_float(value) for value in values), default=0.0)


def _integrated_loudness(log: str) -> float | None:
    values = re.findall(r"\bI:\s*(-?(?:inf|[0-9.]+))\s+LUFS", log or "", re.IGNORECASE)
    for value in reversed(values):
        if value.lower() != "-inf":
            return _float(value)
    return None


def evaluate_video_qa(
    probe: Mapping[str, Any],
    *,
    analysis_log: str = "",
    decode_ok: bool = True,
    subtitle_ass_path: str = "",
    text_boxes: Mapping[str, Mapping[str, Any]] | None = None,
    watermark_detected: bool = False,
) -> VideoQAResult:
    streams = probe.get("streams", []) if isinstance(probe, Mapping) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    media_format = probe.get("format", {}) if isinstance(probe, Mapping) else {}

    format_name = str(media_format.get("format_name", "")).lower()
    duration = _float(media_format.get("duration"))
    size = int(_float(media_format.get("size")))
    width = int(_float(video.get("width")))
    height = int(_float(video.get("height")))
    fps = _rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    video_codec = str(video.get("codec_name", "")).lower()
    pixel_format = str(video.get("pix_fmt", "")).lower()
    audio_codec = str(audio.get("codec_name", "")).lower()
    sample_rate = int(_float(audio.get("sample_rate")))
    channels = int(_float(audio.get("channels")))

    blocking: list[str] = []
    warnings: list[str] = []
    container_valid = bool(("mp4" in format_name or "mov" in format_name) and duration > 0 and size > 1024)
    if not container_valid:
        blocking.append("CONTAINER_INVALID")
    if video_codec != "h264":
        blocking.append("VIDEO_CODEC_INVALID")
    if (width, height) != (1080, 1920):
        blocking.append("VIDEO_RESOLUTION_INVALID")
    if width <= 0 or height <= 0 or abs((width / max(height, 1)) - (9 / 16)) > 0.005:
        blocking.append("VIDEO_ASPECT_RATIO_INVALID")
    if pixel_format != "yuv420p":
        blocking.append("VIDEO_PIXEL_FORMAT_INVALID")
    if abs(fps - 30.0) > 0.05:
        blocking.append("VIDEO_FPS_INVALID")
    if not audio:
        blocking.append("AUDIO_MISSING")
    else:
        if audio_codec != "aac":
            blocking.append("AUDIO_CODEC_INVALID")
        if sample_rate != 48000:
            blocking.append("AUDIO_SAMPLE_RATE_INVALID")
        if channels != 2:
            blocking.append("AUDIO_CHANNELS_INVALID")
    if not decode_ok:
        blocking.append("FFMPEG_DECODE_FAILED")

    safe_errors: list[str] = []
    safe_warnings: list[str] = []
    if subtitle_ass_path:
        subtitle_result = validate_ass_file(subtitle_ass_path)
        safe_errors.extend(subtitle_result.errors)
        safe_warnings.extend(subtitle_result.warnings)
    for kind, box in (text_boxes or {}).items():
        result = validate_element_box(kind, box)
        safe_errors.extend(result.errors)
        safe_warnings.extend(result.warnings)
    safe_zone_ok = not safe_errors
    if not safe_zone_ok:
        blocking.append("SAFE_ZONE_FAILED")
        warnings.extend(safe_errors)
    warnings.extend(safe_warnings)

    max_black = _max_metric(analysis_log, "black_duration")
    max_freeze = _max_metric(analysis_log, "freeze_duration")
    max_silence = _max_metric(analysis_log, "silence_duration")
    integrated_lufs = _integrated_loudness(analysis_log)
    black_frame_ok = max_black < 1.0
    freeze_frame_ok = max_freeze < 8.0
    silence_limit = max(3.0, min(8.0, duration * 0.35))
    silence_ok = max_silence < silence_limit
    loudness_ok = integrated_lufs is not None and -32.0 <= integrated_lufs <= -5.0

    if not black_frame_ok:
        blocking.append("BLACK_FRAME_DETECTED")
    if not freeze_frame_ok:
        blocking.append("FREEZE_FRAME_DETECTED")
    elif max_freeze >= 3.0:
        warnings.append("FREEZE_FRAME_WARNING")
    if not silence_ok:
        blocking.append("LONG_SILENCE_DETECTED")
    elif max_silence >= 2.0:
        warnings.append("SILENCE_WARNING")
    if integrated_lufs is None:
        blocking.append("LOUDNESS_UNMEASURABLE")
    elif not loudness_ok:
        blocking.append("LOUDNESS_OUT_OF_RANGE")
    elif not -18.0 <= integrated_lufs <= -10.0:
        warnings.append("LOUDNESS_WARNING")

    watermark_ok = not bool(watermark_detected)
    if not watermark_ok:
        blocking.append("WATERMARK_DETECTED")

    blocking = list(dict.fromkeys(blocking))
    warnings = list(dict.fromkeys(warnings))
    return VideoQAResult(
        container_valid=container_valid,
        video_codec=video_codec,
        resolution=f"{width}x{height}",
        aspect_ratio="9:16" if width and height and abs((width / height) - (9 / 16)) <= 0.005 else "invalid",
        pixel_format=pixel_format,
        fps=round(fps, 3),
        audio_codec=audio_codec,
        audio_sample_rate=sample_rate,
        audio_channels=channels,
        decode_ok=decode_ok,
        safe_zone_ok=safe_zone_ok,
        black_frame_ok=black_frame_ok,
        freeze_frame_ok=freeze_frame_ok,
        silence_ok=silence_ok,
        loudness_ok=loudness_ok,
        watermark_ok=watermark_ok,
        passed=not blocking,
        blocking_errors=tuple(blocking),
        warnings=tuple(warnings),
        duration=round(duration, 3),
        integrated_lufs=integrated_lufs,
        max_black_seconds=round(max_black, 3),
        max_freeze_seconds=round(max_freeze, 3),
        max_silence_seconds=round(max_silence, 3),
    )


def run_video_qa(
    video_path: str,
    *,
    subtitle_ass_path: str = "",
    text_boxes: Mapping[str, Mapping[str, Any]] | None = None,
    watermark_detected: bool = False,
    timeout: int = 300,
) -> VideoQAResult:
    if not video_path or not os.path.exists(video_path):
        return evaluate_video_qa({}, analysis_log="", decode_ok=False)
    probe_cmd = ffprobe_command(
        "-v", "error",
        "-show_entries",
        "format=format_name,duration,size:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels",
        "-of", "json", video_path,
    )
    try:
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        probe = json.loads(probe_result.stdout) if probe_result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        probe = {}

    analysis_cmd = [
        *ffmpeg_command("-hide_banner", "-nostats", "-v", "info", "-i", video_path),
        "-vf", "blackdetect=d=1.0:pix_th=0.10:pic_th=0.98,freezedetect=n=-50dB:d=2.0",
        "-af", "silencedetect=n=-45dB:d=2.0,ebur128=peak=true",
        "-f", "null", "-",
    ]
    try:
        analysis = subprocess.run(analysis_cmd, capture_output=True, text=True, timeout=timeout)
        analysis_log = f"{analysis.stdout}\n{analysis.stderr}"
        decode_ok = analysis.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        analysis_log = str(exc)
        decode_ok = False
    return evaluate_video_qa(
        probe,
        analysis_log=analysis_log,
        decode_ok=decode_ok,
        subtitle_ass_path=subtitle_ass_path,
        text_boxes=text_boxes,
        watermark_detected=watermark_detected,
    )
