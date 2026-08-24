"""Chuẩn hóa JSON AI mới và cũ về content schema dùng chung."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from shared.core.content_models import (
    BEAT_ROLES,
    CONFIDENCE_LEVELS,
    CONTENT_SCHEMA_VERSION,
    HOOK_TYPES,
    STORY_TYPES,
)


VALID_MUSIC_MOODS = {
    "breaking_tension",
    "serious_warning",
    "neutral_news",
    "positive_upbeat",
    "sensitive_empathy",
    "sports_energy",
    "entertainment_drama",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "có", "co"}:
        return True
    if normalized in {"false", "0", "no", "n", "không", "khong"}:
        return False
    return default


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-ZÀ-ỹ]+", " ", _text(value).lower()).strip()


def _content_id(
    raw: Mapping[str, Any],
    *,
    source_type: str,
    channel_id: str,
    source_url: str,
) -> str:
    existing = _text(raw.get("content_id"))
    if existing:
        return existing
    identity = "|".join(
        (_text(channel_id), _text(source_type), _text(source_url))
    )
    if not identity.replace("|", ""):
        return ""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def infer_story_type(content: Mapping[str, Any]) -> str:
    requested = _text(content.get("story_type")).lower().replace("-", "_").replace(" ", "_")
    if requested in STORY_TYPES:
        return requested

    mood = _text(content.get("music_mood")).lower()
    tone = _text(content.get("tone")).lower()
    combined = " ".join(
        [
            _text(content.get("main_idea")),
            _text(content.get("main_angle")),
            _text(content.get("hook")),
            _text(content.get("title_tiktok")),
        ]
    ).lower()

    if mood == "sports_energy" or any(word in combined for word in ("trận đấu", "cầu thủ", "bàn thắng")):
        return "sports_moment"
    if mood == "entertainment_drama" or any(word in combined for word in ("showbiz", "nghệ sĩ", "ca sĩ")):
        return "entertainment_drama"
    if mood == "breaking_tension":
        return "breaking_update"
    if mood == "serious_warning" or tone == "cảnh báo":
        return "warning"
    if mood == "sensitive_empathy" or tone == "đồng cảm":
        return "human_story"
    if mood == "positive_upbeat" or tone == "tích cực":
        return "achievement"
    if any(word in combined for word in ("so với", "so sánh", "chênh lệch", "giá")):
        return "comparison"
    if any(word in combined for word in ("tranh cãi", "mâu thuẫn", "hai luồng", "phản đối")):
        return "conflict"
    return "explainer"


def _normalize_hook_variants(raw: Mapping[str, Any], selected_hook: str) -> list[dict[str, Any]]:
    variants = []
    seen = set()

    for index, item in enumerate(_list(raw.get("hook_variants"))):
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, Mapping):
            continue

        text = _text(item.get("text") or item.get("hook"))
        key = _normalized_key(text)
        if not text or key in seen:
            continue
        seen.add(key)

        hook_type = _text(item.get("hook_type") or item.get("type") or "result").lower()
        if hook_type not in HOOK_TYPES:
            hook_type = ("result", "conflict", "impact")[min(index, 2)]
        variants.append(
            {
                "text": text,
                "hook_type": hook_type,
                "promise": _text(item.get("promise")),
                "score": _int(item.get("score"), 0, 0, 10),
            }
        )

    selected_key = _normalized_key(selected_hook)
    if selected_hook and selected_key not in seen:
        variants.insert(
            0,
            {
                "text": selected_hook,
                "hook_type": "result",
                "promise": "",
                "score": 0,
            },
        )
    return variants


def _normalize_evidence(raw: Mapping[str, Any], source_url: str) -> list[dict[str, str]]:
    normalized = []
    for item in _list(raw.get("evidence")):
        if isinstance(item, str):
            item = {"claim": item}
        if not isinstance(item, Mapping):
            continue
        confidence = _text(item.get("confidence") or "medium").lower()
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "medium"
        normalized.append(
            {
                "claim": _text(item.get("claim")),
                "source_text": _text(
                    item.get("source_text")
                    or item.get("observed_detail")
                    or item.get("proof")
                ),
                "source_url": source_url or _text(item.get("source_url")),
                "confidence": confidence,
            }
        )
    return normalized


def _looks_sensitive(raw: Mapping[str, Any]) -> bool:
    combined = " ".join(
        _text(raw.get(field_name))
        for field_name in (
            "hook",
            "selected_hook",
            "script_voice",
            "main_idea",
            "main_angle",
            "title_tiktok",
        )
    ).lower()
    sensitive_terms = (
        "tử vong",
        "thiệt mạng",
        "qua đời",
        "thương tích nặng",
        "bị thương nặng",
        "trẻ em gặp nạn",
        "nạn nhân",
        "thi thể",
        "thảm họa",
        "thiên tai",
    )
    return any(term in combined for term in sensitive_terms)


def _normalize_beats(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_beats = _list(raw.get("beats"))
    from_legacy_scenes = not source_beats
    if from_legacy_scenes:
        source_beats = _list(raw.get("scenes") or raw.get("image_prompts"))

    normalized = []
    total = len(source_beats)
    for index, item in enumerate(source_beats):
        if isinstance(item, str):
            item = {"visual_description": item}
        if not isinstance(item, Mapping):
            continue

        role = _text(item.get("role")).lower()
        if role not in BEAT_ROLES:
            if index == 0:
                role = "hook"
            elif index == total - 1:
                role = "payoff"
            else:
                role = "evidence" if from_legacy_scenes else "development"

        must_show = [
            _text(value)
            for value in _list(item.get("must_show"))
            if _text(value)
        ]
        normalized.append(
            {
                "beat_number": index + 1,
                "role": role,
                "duration_hint": _float(item.get("duration_hint"), 2.5, 0.8, 8.0),
                "voice_over": _text(item.get("voice_over")),
                "visual_query": _text(
                    item.get("visual_query")
                    or item.get("visual_description")
                    or item.get("image_prompt")
                ),
                "on_screen_text": _text(item.get("on_screen_text")),
                "motion": _text(item.get("motion") or "static").lower(),
                "transition": _text(item.get("transition") or "cut").lower(),
                "sfx": _text(item.get("sfx")),
                "must_show": must_show,
            }
        )
    return normalized


def normalize_content(
    raw_content: Mapping[str, Any] | None,
    *,
    source_type: str,
    channel_id: str = "",
    source_url: str = "",
) -> dict[str, Any]:
    """Trả về dict mới, giữ field cũ để renderer hiện tại tiếp tục hoạt động."""

    raw = dict(raw_content or {})
    normalized = dict(raw)

    selected_hook = _text(raw.get("selected_hook") or raw.get("hook"))
    hook_variants = _normalize_hook_variants(raw, selected_hook)
    if not selected_hook and hook_variants:
        selected_hook = hook_variants[0]["text"]

    beats = _normalize_beats(raw)
    scenes = [
        {
            "scene_number": beat["beat_number"],
            "voice_over": beat["voice_over"],
            "visual_description": beat["visual_query"],
        }
        for beat in beats
    ]

    music_mood = _text(raw.get("music_mood") or "neutral_news").lower()
    if music_mood not in VALID_MUSIC_MOODS:
        music_mood = "neutral_news"

    authoritative_source_url = _text(source_url) or _text(raw.get("source_url"))
    normalized.update(
        {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "content_id": _content_id(
                raw,
                source_type=_text(source_type),
                channel_id=_text(channel_id),
                source_url=authoritative_source_url,
            ),
            "channel_id": _text(channel_id) or _text(raw.get("channel_id")),
            "source_type": _text(source_type) or _text(raw.get("source_type")),
            "source_url": authoritative_source_url,
            "story_type": infer_story_type(raw),
            "main_angle": _text(raw.get("main_angle") or raw.get("main_idea")),
            "audience_payoff": _text(
                raw.get("audience_payoff")
                or raw.get("payoff")
            ),
            "hook_variants": hook_variants,
            "selected_hook": selected_hook,
            "selected_hook_reason": _text(raw.get("selected_hook_reason")),
            "hook": selected_hook,
            "script_voice": _text(raw.get("script_voice") or raw.get("script")),
            "title_tiktok": _text(raw.get("title_tiktok")),
            "evidence": _normalize_evidence(raw, authoritative_source_url),
            "beats": beats,
            "scenes": scenes,
            "retention_risks": [
                _text(item) for item in _list(raw.get("retention_risks")) if _text(item)
            ],
            "risk_flags": [
                _text(item) for item in _list(raw.get("risk_flags")) if _text(item)
            ],
            "should_make_video": _bool(raw.get("should_make_video"), True),
            "topic_fit": _bool(raw.get("topic_fit"), True),
            "have_frame": _bool(raw.get("have_frame"), False),
            "is_sensitive": (
                _bool(raw.get("is_sensitive"), False)
                or _looks_sensitive(raw)
            ),
            "music_mood": music_mood,
            "music_energy": _int(raw.get("music_energy"), 2, 1, 3),
            "subtitle_style": (
                _text(raw.get("subtitle_style") or "keyword_highlight").lower()
                if _text(raw.get("subtitle_style") or "keyword_highlight").lower()
                in {"normal", "keyword_highlight"}
                else "keyword_highlight"
            ),
            "cta_mode": (
                _text(raw.get("cta_mode") or "specific").lower()
                if _text(raw.get("cta_mode") or "specific").lower()
                in {"none", "specific"}
                else "specific"
            ),
            "target_duration_seconds": _int(
                raw.get("target_duration_seconds"), 0, 0, 60,
            ),
            "visual_beat_count": len(beats),
            "experiment_id": _text(raw.get("experiment_id")),
            "experiment_variant": _text(raw.get("experiment_variant")),
            "experiment_variable": _text(raw.get("experiment_variable")),
            "experiment_value": _text(raw.get("experiment_value")),
            "quality_score": _int(raw.get("quality_score"), 5, 0, 10),
            "tone": _text(raw.get("tone") or "Trung tính"),
            "topic_fit_reason": _text(raw.get("topic_fit_reason")),
            "skip_reason": _text(raw.get("skip_reason")),
        }
    )
    return normalized
