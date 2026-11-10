"""Evidence gate cho luồng production job JSON v1 — Giai đoạn 5.

Theo ``KE_HOACH_NANG_CAP_TOOL_VIDEO_TIN_TUC.md`` §8: bật EvidenceGuard cho
tin tài chính/pháp luật/sức khỏe và mọi nội dung có số liệu; bài có số liệu
không có evidence hợp lệ bị đưa về hàng chờ duyệt (``needs_review``), operator
duyệt rõ ràng thì mới được render.

Khác với ``evidence_guard.guard_evidence`` (dành cho content model cũ với
``claim_register``/``evidence`` đầy đủ), gate này làm việc trực tiếp trên
storyboard v1: câu có số liệu trong hook/script/voice_over phải được hỗ trợ
bởi ``source_text`` (trích bài nguồn), label số trong ``on_screen_text``/
``must_show`` phải khớp số trong ``source_text``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from shared.core.evidence_guard import (
    _numeric_key,
    _numeric_values,
    _plain,
    _supported_by_source,
)

_HIGH_RISK_TERMS = (
    "tai chinh", "chung khoan", "kinh te", "tien te", "ngan hang",
    "phap luat", "to an", "luat su", "an ninh",
    "suc khoe", "y te", "benh", "thuoc", "tham my", "dao keo",
)

_SENTENCE_SPLIT = re.compile(r"(?:[.!?]+\s+|\n+)")


def high_risk_category(profile: Mapping[str, Any] | None) -> bool:
    """Kênh thuộc nhóm tin rủi ro cao (tài chính/pháp luật/sức khỏe)."""

    if not isinstance(profile, Mapping):
        return False
    text = _plain(" ".join(
        str(profile.get(key) or "")
        for key in (
            "topic", "channel_name", "niche", "audience",
            "content_promise", "risk_flags",
        )
    ))
    return any(term in text for term in _HIGH_RISK_TERMS)


def _prose_sentences(storyboard: Mapping[str, Any]) -> list[str]:
    surfaces: list[str] = []
    for field_name in ("hook", "script_voice"):
        surfaces.extend(
            part.strip()
            for part in _SENTENCE_SPLIT.split(str(storyboard.get(field_name) or ""))
            if part.strip()
        )
    for beat in storyboard.get("beats") or []:
        if not isinstance(beat, Mapping):
            continue
        surfaces.extend(
            part.strip()
            for part in _SENTENCE_SPLIT.split(str(beat.get("voice_over") or ""))
            if part.strip()
        )
    return surfaces


def _number_labels(storyboard: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    for beat in storyboard.get("beats") or []:
        if not isinstance(beat, Mapping):
            continue
        for field_name in ("on_screen_text", "must_show"):
            value = beat.get(field_name)
            values = value if isinstance(value, list) else [value]
            labels.extend(str(item).strip() for item in values if str(item or "").strip())
    return labels


def numeric_claims(storyboard: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Câu/label có chứa số: (prose_sentences, labels)."""

    prose = [s for s in _prose_sentences(storyboard) if any(c.isdigit() for c in s)]
    labels = [l for l in _number_labels(storyboard) if any(c.isdigit() for c in l)]
    return prose, labels


@dataclass(frozen=True)
class EvidenceGateReport:
    required: bool
    passed: bool
    high_risk: bool
    prose_claim_count: int
    label_claim_count: int
    unsupported: tuple[str, ...]
    reason: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "passed": self.passed,
            "high_risk": self.high_risk,
            "prose_claim_count": self.prose_claim_count,
            "label_claim_count": self.label_claim_count,
            "unsupported": list(self.unsupported),
            "reason": self.reason,
            "warnings": list(self.warnings),
        }


def evaluate_evidence(
    storyboard: Mapping[str, Any],
    *,
    source_text: str = "",
    source_url: str = "",
    profile: Mapping[str, Any] | None = None,
) -> EvidenceGateReport:
    """Trả về kết quả gate: thiếu evidence hợp lệ -> passed=False (chờ duyệt)."""

    prose, labels = numeric_claims(storyboard)
    high_risk = high_risk_category(profile)
    required = bool(prose or labels) or high_risk
    warnings: list[str] = []
    if not required:
        return EvidenceGateReport(
            required=False, passed=True, high_risk=False,
            prose_claim_count=0, label_claim_count=0,
            unsupported=(), reason="",
        )
    if not str(source_text or "").strip():
        return EvidenceGateReport(
            required=True, passed=False, high_risk=high_risk,
            prose_claim_count=len(prose), label_claim_count=len(labels),
            unsupported=tuple(prose + labels),
            reason="EVIDENCE_MISSING",
            warnings=warnings,
        )
    if not str(source_url or "").strip():
        warnings.append("SOURCE_URL_MISSING")

    unsupported: list[str] = [
        sentence for sentence in prose
        if not _supported_by_source(sentence, source_text)
    ]
    source_numbers = {
        _numeric_key(value) for value in _numeric_values(source_text)
    }
    for label in labels:
        label_numbers = {
            _numeric_key(value) for value in _numeric_values(label)
        }
        if label_numbers and not label_numbers <= source_numbers:
            unsupported.append(label)
    passed = not unsupported
    return EvidenceGateReport(
        required=True, passed=passed, high_risk=high_risk,
        prose_claim_count=len(prose), label_claim_count=len(labels),
        unsupported=tuple(unsupported),
        reason="" if passed else "EVIDENCE_UNSUPPORTED",
        warnings=tuple(warnings),
    )
