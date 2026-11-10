"""Kiểm định JSON kịch bản khoá (Article JSON v1) trước khi đưa vào dựng video.

Theo ``BRIEF_AGENT_DUNG_VIDEO_TIN_TUC.md``: JSON do ChatGPT trả về là kịch bản
khoá — Tool Media không gọi AI lần hai để sửa. JSON sai schema thì chặn và
để operator sửa trực tiếp JSON rồi import lại.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from shared.core.content_normalizer import VALID_MUSIC_MOODS
from shared.core.content_validator import ValidationIssue

# BRIEF §2: 7-9 beats; sai số lượng là chặn.
LOCKED_SCRIPT_BEAT_RANGE = (7, 9)

# BRIEF §1: 45-70 giây, mặc định 52 giây.
DEFAULT_TARGET_DURATION_SEC = 52.0

# BRIEF §2: tổng thời lượng lệch quá 15% so với hồ sơ kênh là chặn.
DURATION_TOLERANCE = 0.15

PROFILE_VIDEO_LENGTH_RANGES = {
    "30-45s": (30.0, 45.0),
    "45-60s": (45.0, 60.0),
    "60-90s": (60.0, 90.0),
    "90-120s": (90.0, 120.0),
}

_DURATION_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")

# Ước lượng tốc độ đọc tiếng Việt để preview storyboard (~2.8 từ/giây).
ESTIMATED_WORDS_PER_SECOND = 2.8


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _coerce_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _resolve_beat_duration(item: Mapping[str, Any]) -> float | None:
    """Ưu tiên duration_hint; nếu thiếu thì tính từ end_sec - start_sec."""
    hint = _coerce_float(item.get("duration_hint"))
    if hint is not None and hint > 0:
        return hint
    start = _coerce_float(item.get("start_sec"))
    end = _coerce_float(item.get("end_sec"))
    if start is not None and end is not None and end > start:
        return round(end - start, 3)
    return hint


def _resolve_visual_query(item: Mapping[str, Any]) -> str:
    """Trả về visual_query; nếu trống nhưng có visual_fallback thì suy ra tiền tố card."""
    vq = _text(item.get("visual_query"))
    if vq:
        return vq
    fb = _text(item.get("visual_fallback"))
    if not fb:
        return ""
    lower = fb.lower()
    if any(k in lower for k in ("bản đồ", "sơ đồ địa điểm", "vị trí địa lý", "map")):
        return f"MAP GRAPHIC: {fb}"
    if any(k in lower for k in ("trích dẫn", "phát ngôn", "quote")):
        return f"QUOTE CARD: {fb}"
    if (
        any(k in lower for k in ("thẻ số", "so sánh", "tỷ lệ", "đồng/", "%", "mức trần"))
        or re.search(r"\d+[.,]\d+", fb)
    ):
        return f"DATA GRAPHIC: {fb}"
    return f"FACT CARD: {fb}"


def profile_target_duration(profile: Mapping[str, Any] | None) -> float | None:
    """Mốc giữa của dải `video_length` trong hồ sơ kênh, nếu parse được."""
    if not isinstance(profile, Mapping):
        return None
    raw = _text(profile.get("video_length"))
    match = _DURATION_RANGE_RE.search(raw)
    if not match:
        return None
    low, high = float(match.group(1)), float(match.group(2))
    if low <= 0 or high < low:
        return None
    return (low + high) / 2.0


@dataclass
class LockedScriptReport:
    passed: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    beat_count: int = 0
    total_hint_seconds: float = 0.0
    target_duration_seconds: float = DEFAULT_TARGET_DURATION_SEC
    duration_deviation: float | None = None
    channel_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "beat_count": self.beat_count,
            "total_hint_seconds": round(self.total_hint_seconds, 2),
            "target_duration_seconds": self.target_duration_seconds,
            "duration_deviation": (
                round(self.duration_deviation, 4)
                if self.duration_deviation is not None
                else None
            ),
            "channel_id": self.channel_id,
        }


def _validate_beats(
    raw: Mapping[str, Any],
    *,
    add_error,
    add_warning,
) -> tuple[int, float]:
    beats_raw = raw.get("beats")
    beats = beats_raw if isinstance(beats_raw, list) else []
    count = len(beats)
    low, high = LOCKED_SCRIPT_BEAT_RANGE
    if not low <= count <= high:
        add_error(
            "BEAT_COUNT_OUT_OF_RANGE",
            f"Cần {low}-{high} beats, JSON có {count}.",
            "beats",
        )

    total = 0.0
    for index, item in enumerate(beats):
        label = f"beats[{index}]"
        if not isinstance(item, Mapping):
            add_error("BEAT_INVALID", "Beat không phải object.", label)
            continue

        beat_number = _coerce_float(item.get("beat_number"))
        if beat_number is not None and beat_number != index + 1:
            add_warning(
                "BEAT_NUMBER_MISMATCH",
                f"beat_number={beat_number:g} nhưng vị trí là {index + 1}.",
                f"{label}.beat_number",
            )

        duration_hint = _resolve_beat_duration(item)
        if duration_hint is None or duration_hint <= 0 or duration_hint > 15:
            add_error(
                "BEAT_DURATION_INVALID",
                f"duration_hint không hợp lệ: {item.get('duration_hint')!r} (cần 0 < x <= 15).",
                f"{label}.duration_hint",
            )
        else:
            total += duration_hint
            if duration_hint < 2.0 or duration_hint > 8.0:
                add_warning(
                    "BEAT_DURATION_OUT_OF_HINT_RANGE",
                    f"duration_hint={duration_hint:g}s nằm ngoài dải khuyến nghị 2-8s.",
                    f"{label}.duration_hint",
                )

        if not _text(item.get("voice_over")):
            add_warning(
                "BEAT_VOICE_OVER_EMPTY",
                "voice_over trống; cảnh này sẽ không có lời thoại.",
                f"{label}.voice_over",
            )
        if not _text(item.get("visual_query")) and not _text(item.get("visual_fallback")):
            add_warning(
                "VISUAL_QUERY_EMPTY",
                "visual_query trống; renderer sẽ phải tự chọn graphic fallback.",
                f"{label}.visual_query",
            )
        must_show = item.get("must_show")
        if must_show is not None and not isinstance(must_show, list):
            add_error(
                "MUST_SHOW_INVALID",
                "must_show phải là danh sách chuỗi.",
                f"{label}.must_show",
            )

    return count, total


def validate_locked_script(
    raw: Any,
    *,
    profile: Mapping[str, Any] | None = None,
    channel_id: str = "",
) -> LockedScriptReport:
    """Trả về report chặn/cho phép theo luật BRIEF §2. Không sửa JSON."""
    if not isinstance(raw, Mapping):
        return LockedScriptReport(
            passed=False,
            errors=[
                ValidationIssue(
                    "SCRIPT_NOT_OBJECT",
                    "JSON gốc phải là một object, không phải mảng hoặc chuỗi.",
                    "$",
                    "error",
                )
            ],
            channel_id=_text(channel_id),
        )

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    def add_error(code: str, message: str, field_name: str) -> None:
        errors.append(ValidationIssue(code, message, field_name, "error"))

    def add_warning(code: str, message: str, field_name: str) -> None:
        warnings.append(ValidationIssue(code, message, field_name, "warning"))

    clean_channel = _text(channel_id).replace("@", "") or _text(
        raw.get("channel_id") or raw.get("id_tiktok")
    ).replace("@", "")

    schema_version = raw.get("schema_version")
    if schema_version in (None, ""):
        add_warning(
            "SCHEMA_VERSION_MISSING",
            "Thiếu schema_version; mặc định hiểu là v1.",
            "schema_version",
        )
    else:
        parsed_version = _coerce_float(schema_version)
        if parsed_version is None or int(parsed_version) != 1:
            add_error(
                "SCHEMA_VERSION_UNSUPPORTED",
                f"schema_version={schema_version!r} không được hỗ trợ; luồng hiện tại chỉ nhận JSON v1.",
                "schema_version",
            )
            return LockedScriptReport(
                passed=False,
                errors=errors,
                warnings=warnings,
                channel_id=clean_channel,
            )

    if not _text(raw.get("hook") or raw.get("selected_hook")):
        add_error("HOOK_MISSING", "Thiếu hook — không có voice 0-2 giây đầu.", "hook")
    if not _text(raw.get("script_voice")):
        add_error(
            "SCRIPT_VOICE_MISSING",
            "Thiếu script_voice — không có nội dung voice chính.",
            "script_voice",
        )

    beat_count, total_hint = _validate_beats(
        raw, add_error=add_error, add_warning=add_warning
    )

    music_mood = _text(raw.get("music_mood")).lower()
    if music_mood and music_mood not in VALID_MUSIC_MOODS:
        add_warning(
            "MUSIC_MOOD_UNKNOWN",
            f"music_mood={music_mood!r} không thuộc danh sách hợp lệ; sẽ fallback về neutral_news.",
            "music_mood",
        )

    if not clean_channel:
        add_warning(
            "CHANNEL_ID_MISSING",
            "Thiếu channel_id trong JSON và trong yêu cầu; không đối chiếu được hồ sơ kênh.",
            "channel_id",
        )

    target = profile_target_duration(profile)
    if target is None:
        target = DEFAULT_TARGET_DURATION_SEC
        if isinstance(profile, Mapping) and _text(profile.get("video_length")):
            add_warning(
                "PROFILE_DURATION_UNPARSED",
                f"video_length={_text(profile.get('video_length'))!r} không parse được; dùng mặc định {target:g}s.",
                "profile.video_length",
            )

    deviation: float | None = None
    if total_hint > 0:
        deviation = abs(total_hint - target) / target
        if deviation > DURATION_TOLERANCE:
            add_error(
                "DURATION_PROFILE_MISMATCH",
                (
                    f"Tổng duration_hint={total_hint:.1f}s lệch "
                    f"{deviation * 100:.0f}% so với mục tiêu {target:.1f}s "
                    f"(ngưỡng cho phép {DURATION_TOLERANCE * 100:.0f}%)."
                ),
                "beats",
            )

    return LockedScriptReport(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        beat_count=beat_count,
        total_hint_seconds=total_hint,
        target_duration_seconds=target,
        duration_deviation=deviation,
        channel_id=clean_channel,
    )


def build_storyboard(
    raw: Mapping[str, Any],
    *,
    report: LockedScriptReport | None = None,
) -> dict[str, Any]:
    """Storyboard preview: timeline suy từ duration_hint, chưa biết duration TTS thật.

    Thời lượng thật chỉ chốt được sau khi TTS xong (BRIEF §9), nên mọi mốc
    thời gian ở đây chỉ mang tính preview.
    """

    beats_raw = raw.get("beats")
    beats = beats_raw if isinstance(beats_raw, list) else []
    cursor = 0.0
    beat_items: list[dict[str, Any]] = []
    for index, item in enumerate(beats):
        if not isinstance(item, Mapping):
            continue
        duration_hint = _resolve_beat_duration(item) or 0.0
        if duration_hint <= 0 or duration_hint > 15:
            duration_hint = 0.0
        start = round(cursor, 2)
        end = round(cursor + duration_hint, 2)
        cursor = end
        voice_over = _text(item.get("voice_over"))
        words = len(voice_over.split())
        must_show_raw = item.get("must_show")
        must_show = (
            [_text(value) for value in must_show_raw if _text(value)]
            if isinstance(must_show_raw, list)
            else []
        )
        beat_items.append(
            {
                "beat_number": index + 1,
                "start_sec": start,
                "end_sec": end,
                "duration_hint": round(duration_hint, 2),
                "role": _text(item.get("role")),
                "voice_over": voice_over,
                "on_screen_text": _text(item.get("on_screen_text")),
                "visual_query": _resolve_visual_query(item),
                "visual_fallback": _text(item.get("visual_fallback")),
                "motion": _text(item.get("motion")),
                "transition": _text(item.get("transition")),
                "must_show": must_show,
                "estimated_voice_seconds": round(words / ESTIMATED_WORDS_PER_SECOND, 2),
            }
        )

    source = raw.get("source") if isinstance(raw.get("source"), Mapping) else {}
    return {
        "timeline_basis": "duration_hint",
        "beat_count": len(beat_items),
        "total_hint_seconds": round(cursor, 2),
        "target_duration_seconds": (
            report.target_duration_seconds
            if report is not None
            else DEFAULT_TARGET_DURATION_SEC
        ),
        "hook": _text(raw.get("hook") or raw.get("selected_hook")),
        "script_voice": _text(raw.get("script_voice")),
        "title_tiktok": _text(raw.get("title_tiktok")),
        "source_url": _text(raw.get("source_url") or source.get("url")),
        "music": {
            "mood": _text(raw.get("music_mood")).lower() or "neutral_news",
            "energy": raw.get("music_energy", 2),
            "is_sensitive": _coerce_bool(raw.get("is_sensitive")),
        },
        "beats": beat_items,
    }
