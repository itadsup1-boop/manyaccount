"""Các model nội dung dùng chung cho mọi pipeline video ngắn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


CONTENT_SCHEMA_VERSION = 1

STORY_TYPES = (
    "breaking_update",
    "warning",
    "explainer",
    "conflict",
    "human_story",
    "achievement",
    "comparison",
    "sports_moment",
    "entertainment_drama",
)

HOOK_TYPES = (
    "result",
    "conflict",
    "impact",
    "question",
    "warning",
    "number",
    "curiosity",
)

BEAT_ROLES = (
    "hook",
    "context",
    "evidence",
    "development",
    "turn",
    "payoff",
    "close",
)

CONFIDENCE_LEVELS = ("high", "medium", "low")
CLAIM_TYPES = (
    "fact",
    "number",
    "date",
    "location",
    "attribution",
    "observation",
    "quote",
    "inference",
)


@dataclass
class HookVariant:
    text: str = ""
    hook_type: str = "result"
    promise: str = ""
    score: int = 0

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "HookVariant":
        return cls(
            text=str(value.get("text", "")).strip(),
            hook_type=str(value.get("hook_type", "result")).strip(),
            promise=str(value.get("promise", "")).strip(),
            score=int(value.get("score", 0) or 0),
        )


@dataclass
class EvidenceItem:
    claim: str = ""
    source_text: str = ""
    source_url: str = ""
    confidence: str = "medium"
    claim_id: str = ""
    claim_type: str = "fact"
    numeric_values: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceItem":
        numeric_values = value.get("numeric_values") or value.get("numbers") or []
        if isinstance(numeric_values, str):
            numeric_values = [numeric_values]
        if not isinstance(numeric_values, list):
            numeric_values = []
        return cls(
            claim_id=str(value.get("claim_id", "")).strip(),
            claim=str(value.get("claim", "")).strip(),
            claim_type=str(value.get("claim_type", "fact")).strip(),
            numeric_values=[str(item).strip() for item in numeric_values if str(item).strip()],
            source_text=str(value.get("source_text", "")).strip(),
            source_url=str(value.get("source_url", "")).strip(),
            confidence=str(value.get("confidence", "medium")).strip(),
        )


@dataclass
class ContentBeat:
    beat_number: int = 1
    role: str = "development"
    duration_hint: float = 2.5
    voice_over: str = ""
    visual_query: str = ""
    on_screen_text: str = ""
    motion: str = "static"
    transition: str = "cut"
    sfx: str = ""
    must_show: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContentBeat":
        must_show = value.get("must_show", [])
        if not isinstance(must_show, list):
            must_show = [must_show] if must_show else []
        try:
            duration_hint = float(value.get("duration_hint", 2.5) or 2.5)
        except (TypeError, ValueError):
            duration_hint = 2.5
        try:
            beat_number = int(value.get("beat_number", 1) or 1)
        except (TypeError, ValueError):
            beat_number = 1
        return cls(
            beat_number=beat_number,
            role=str(value.get("role", "development")).strip(),
            duration_hint=duration_hint,
            voice_over=str(value.get("voice_over", "")).strip(),
            visual_query=str(value.get("visual_query", "")).strip(),
            on_screen_text=str(value.get("on_screen_text", "")).strip(),
            motion=str(value.get("motion", "static")).strip(),
            transition=str(value.get("transition", "cut")).strip(),
            sfx=str(value.get("sfx", "")).strip(),
            must_show=[str(item).strip() for item in must_show if str(item).strip()],
        )


@dataclass
class ContentPlan:
    schema_version: int = CONTENT_SCHEMA_VERSION
    content_id: str = ""
    channel_id: str = ""
    source_type: str = ""
    source_url: str = ""
    fact_sheet: dict[str, Any] = field(default_factory=dict)
    story_type: str = "explainer"
    main_angle: str = ""
    audience_payoff: str = ""
    hook_variants: list[HookVariant] = field(default_factory=list)
    selected_hook: str = ""
    selected_hook_reason: str = ""
    script_voice: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    beats: list[ContentBeat] = field(default_factory=list)
    retention_risks: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    subtitle_style: str = "keyword_highlight"
    cta_mode: str = "specific"
    target_duration_seconds: int = 0
    visual_beat_count: int = 0
    experiment_id: str = ""
    experiment_variant: str = ""
    experiment_variable: str = ""
    experiment_value: str = ""
    claim_register: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
