"""Deterministic editorial quality gate, independent of the AI self-score."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EditorialQualityReport:
    score: int
    passed: bool
    threshold: int
    breakdown: dict[str, int]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


def _clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _scaled(value: Any, source_max: int, target_max: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return _clamp(numeric / max(1, source_max) * target_max, 0, target_max)


def _report_value(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, Mapping):
        return report.get(name, default)
    return getattr(report, name, default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
    return bool(value)


def _visual_grounding_score(content: Mapping[str, Any]) -> int:
    beats = [
        beat for beat in (content.get("beats") or [])
        if isinstance(beat, Mapping)
    ]
    if not beats:
        return 0
    visual_count = sum(bool(str(beat.get("visual_query") or "").strip()) for beat in beats)
    must_show_count = sum(bool(beat.get("must_show")) for beat in beats)
    visual_ratio = visual_count / len(beats)
    must_show_bonus = 0.2 if must_show_count >= max(1, len(beats) // 2) else 0.0
    return _clamp((visual_ratio + must_show_bonus) * 10, 0, 10)


def _last_beat_role(content: Mapping[str, Any]) -> str:
    beats = content.get("beats") or []
    for beat in reversed(beats):
        if isinstance(beat, Mapping):
            return str(beat.get("role") or "").strip().lower()
    return ""


def evaluate_editorial_quality(
    content: Mapping[str, Any],
    *,
    validation_report: Any,
    evidence_report: Any | None = None,
    rights_report: Any | None = None,
    threshold: int = 70,
) -> EditorialQualityReport:
    """Score content using deterministic reports and fields only.

    ``content['quality_score']`` is intentionally never read here.
    """
    try:
        normalized_threshold = _clamp(int(threshold))
    except (TypeError, ValueError):
        normalized_threshold = 70

    validation_breakdown = _report_value(
        validation_report, "score_breakdown", {}
    ) or {}
    if not isinstance(validation_breakdown, Mapping):
        validation_breakdown = {}
    errors = list(_report_value(validation_report, "errors", ()) or ())
    warnings = list(_report_value(validation_report, "warnings", ()) or ())

    topic_fit = _as_bool(content.get("topic_fit"), True)
    should_make_video = _as_bool(content.get("should_make_video"), True)
    topic_score = 20 if topic_fit and should_make_video else 0

    hook_score = _scaled(validation_breakdown.get("hook", 0), 25, 12)
    payoff_score = 8 if (
        str(content.get("audience_payoff") or "").strip()
        and (content.get("beats") or [])
        and _last_beat_role(content) in {"payoff", "close"}
    ) else 0
    hook_payoff_score = hook_score + payoff_score

    script_clarity_score = _scaled(
        validation_breakdown.get("clarity", 0), 15, 15,
    )

    if evidence_report is not None:
        evidence_score = _scaled(_report_value(evidence_report, "score", 0), 100, 25)
    else:
        evidence_score = _scaled(validation_breakdown.get("evidence", 0), 20, 25)

    visual_score = _visual_grounding_score(content)

    rights_passed = bool(_report_value(rights_report, "passed", True))
    rights_review = bool(_report_value(rights_report, "requires_review", False))
    rights_status = str(
        _report_value(rights_report, "status", "unknown") or "unknown"
    ).lower()
    if not rights_passed:
        safety_score = 0
    elif rights_status in {"owned", "licensed", "permission", "public_domain", "remix_allowed"}:
        safety_score = 10
    else:
        safety_score = 7 if rights_review or rights_status == "unknown" else 8

    if _as_bool(content.get("is_sensitive")):
        try:
            music_energy = int(content.get("music_energy") or 2)
        except (TypeError, ValueError):
            music_energy = 2
        music_ok = (
            str(content.get("music_mood") or "") == "sensitive_empathy"
            and music_energy == 1
        )
        if not music_ok:
            safety_score = 0

    breakdown = {
        "evidence": evidence_score,
        "topic_fit": topic_score,
        "hook_payoff": hook_payoff_score,
        "script_clarity": script_clarity_score,
        "visual_grounding": visual_score,
        "safety_rights": safety_score,
    }
    score = _clamp(sum(breakdown.values()), 0, 100)

    reasons: list[str] = []
    if not topic_fit:
        reasons.append("Sai định vị chủ đề kênh.")
    if not should_make_video:
        reasons.append("Nội dung được đánh dấu không nên sản xuất.")
    if evidence_score < 18:
        reasons.append("Evidence chưa đủ mạnh.")
    if hook_payoff_score < 14:
        reasons.append("Hook hoặc payoff chưa đủ rõ.")
    if script_clarity_score < 11:
        reasons.append("Script chưa đủ rõ hoặc còn lỗi nhịp đọc.")
    if visual_score < 8:
        reasons.append("Visual beats chưa được mô tả đủ cụ thể.")
    if safety_score < 10:
        reasons.append("Nguồn/quyền sử dụng hoặc safety chưa được xác minh đầy đủ.")
    if errors:
        reasons.append(f"ContentValidator còn {len(errors)} lỗi.")
    elif warnings:
        reasons.append(f"ContentValidator còn {len(warnings)} cảnh báo.")

    passed = (
        bool(_report_value(validation_report, "passed", False))
        and bool(_report_value(evidence_report, "passed", True))
        and rights_passed
        and topic_fit
        and should_make_video
        and score >= normalized_threshold
    )
    return EditorialQualityReport(
        score=score,
        passed=passed,
        threshold=normalized_threshold,
        breakdown=breakdown,
        reasons=tuple(reasons),
    )


def summarize_quality_gate(report: EditorialQualityReport) -> str:
    if report.passed:
        return f"Editorial quality {report.score}/100 đạt ngưỡng {report.threshold}."
    reason = " ".join(report.reasons) or "Điểm editorial quality dưới ngưỡng."
    return f"Editorial quality {report.score}/100 dưới ngưỡng {report.threshold}. {reason}"
