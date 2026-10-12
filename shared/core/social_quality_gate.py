"""Deterministic quality gate for TikTok/Facebook source videos.

The gate deliberately does not read ``quality_score`` from an AI response.
It combines the existing validator/evidence/visual/rights reports with
short-form video structure checks and a transparent evidence-pack score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


_ALLOWED_SOURCE_TYPES = {"tiktok", "facebook", "video"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _report_value(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, Mapping):
        return report.get(name, default)
    return getattr(report, name, default)


def _clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(round(value))))


@dataclass(frozen=True)
class SocialQualityReport:
    source_type: str
    score: int
    passed: bool
    threshold: int
    frame_mode: bool
    breakdown: dict[str, int]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        result["warnings"] = list(self.warnings)
        return result


@dataclass(frozen=True)
class SocialRenderContractReport:
    passed: bool
    score: int
    source_type: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


def evaluate_social_render_contract(
    *,
    source_type: str,
    source_url: str,
    title: str,
    script: str,
    frame_mode: bool = False,
    title_frame_available: bool = True,
    content_frame_available: bool = True,
    subtitle_style: str = "keyword_highlight",
    threshold: int = 70,
) -> SocialRenderContractReport:
    """Validate legacy Sheet-driven routes before they render.

    The legacy auto-clone path does not always carry the full normalized AI
    object, so it still receives an independent render contract gate rather
    than silently bypassing short-form quality checks.
    """
    reasons: list[str] = []
    title_words = len(_text(title).split())
    script_words = len(_text(script).split())
    score = 0
    if 3 <= title_words <= 16:
        score += 30
    elif title_words:
        score += 15
        reasons.append("Title phải ngắn, rõ và có 3–16 từ.")
    else:
        reasons.append("Thiếu title/hook cho video nguồn.")
    if script_words >= 8:
        score += 35
    elif script_words >= 3:
        score += 15
        reasons.append("Script quá ngắn để tạo content frame có ý nghĩa.")
    else:
        reasons.append("Thiếu script content.")
    if source_url:
        score += 10
    else:
        reasons.append("Thiếu URL nguồn để truy vết video.")
    if subtitle_style in {"normal", "keyword_highlight"}:
        score += 10
    else:
        reasons.append("subtitle_style không hợp lệ.")
    if frame_mode:
        if title_frame_available and content_frame_available:
            score += 15
        else:
            reasons.append("Frame mode yêu cầu đủ title frame và content frame.")
    else:
        score += 15
    try:
        normalized_threshold = _clamp(int(threshold))
    except (TypeError, ValueError):
        normalized_threshold = 70
    return SocialRenderContractReport(
        passed=not reasons and score >= normalized_threshold,
        score=_clamp(score),
        source_type=_text(source_type).lower() or "video",
        reasons=tuple(reasons),
    )


def summarize_social_render_contract(report: SocialRenderContractReport) -> str:
    if report.passed:
        return f"Render contract {report.score}/100 đạt."
    return f"Render contract {report.score}/100 không đạt: {'; '.join(report.reasons)}"


def _hook_score(content: Mapping[str, Any]) -> int:
    hook = _text(content.get("selected_hook") or content.get("hook"))
    words = [word for word in hook.split() if word]
    if 3 <= len(words) <= 16:
        return 10
    if words:
        return 5
    return 0


def _beat_score(content: Mapping[str, Any]) -> int:
    beats = [item for item in (content.get("beats") or []) if isinstance(item, Mapping)]
    if not beats:
        return 0
    complete = sum(
        bool(_text(item.get("voice_over")))
        and bool(_text(item.get("visual_query")))
        for item in beats
    )
    return _clamp(complete / len(beats) * 10, 0, 10)


def evaluate_social_quality(
    content: Mapping[str, Any],
    *,
    source_type: str,
    validation_report: Any | None = None,
    evidence_report: Any | None = None,
    visual_report: Any | None = None,
    rights_report: Any | None = None,
    evidence_pack: Mapping[str, Any] | Any | None = None,
    frame_mode: bool = False,
    title_frame_available: bool = True,
    content_frame_available: bool = True,
    threshold: int = 70,
) -> SocialQualityReport:
    """Evaluate social video quality independently of any AI self-score."""
    normalized_source = _text(source_type).lower() or "video"
    if normalized_source not in _ALLOWED_SOURCE_TYPES:
        normalized_source = "video"
    try:
        normalized_threshold = _clamp(int(threshold))
    except (TypeError, ValueError):
        normalized_threshold = 70

    reasons: list[str] = []
    warnings: list[str] = []
    validation_passed = bool(_report_value(validation_report, "passed", False))
    evidence_passed = bool(_report_value(evidence_report, "passed", False))
    visual_passed = (
        True if visual_report is None
        else bool(_report_value(visual_report, "passed", False))
    )
    rights_passed = True if rights_report is None else bool(
        _report_value(rights_report, "passed", False)
    )

    validation_breakdown = _report_value(validation_report, "score_breakdown", {}) or {}
    try:
        validation_score = sum(int(value or 0) for value in validation_breakdown.values())
    except (AttributeError, TypeError, ValueError):
        validation_score = 0
    editorial_component = _clamp(validation_score / 100 * 45, 0, 45)

    evidence_score = _report_value(evidence_report, "score", 0) or 0
    evidence_component = _clamp(float(evidence_score) / 100 * 15, 0, 15)
    visual_score = _report_value(visual_report, "score", 0) if visual_report is not None else 0
    visual_component = _clamp(float(visual_score or 0) / 100 * 10, 0, 10)
    hook_component = _hook_score(content)
    beat_component = _beat_score(content)

    pack_mapping = evidence_pack if isinstance(evidence_pack, Mapping) else {}
    coverage = pack_mapping.get("coverage_score", 0)
    try:
        evidence_pack_component = _clamp(float(coverage) / 100 * 5, 0, 5)
    except (TypeError, ValueError):
        evidence_pack_component = 0

    frame_component = 5
    if frame_mode and (not title_frame_available or not content_frame_available):
        frame_component = 0
        reasons.append("Title/content frame được yêu cầu nhưng asset chưa đầy đủ.")

    if not validation_passed:
        reasons.append("ContentValidator chưa đạt.")
    if not evidence_passed:
        reasons.append("EvidenceGuard chưa đạt.")
    if not visual_passed:
        reasons.append("Visual grounding chưa đạt.")
    if not rights_passed:
        reasons.append("Nguồn video không đạt quyền sử dụng.")
    if hook_component < 10:
        reasons.append("Hook chưa đủ ngắn và rõ cho video ngắn.")
    if beat_component < 7:
        reasons.append("Beat video thiếu voice_over hoặc visual_query cụ thể.")

    if coverage < 100:
        warnings.append(
            "Evidence pack chưa đủ transcript/OCR; không được coi caption là toàn bộ nội dung video."
        )

    score = _clamp(
        editorial_component
        + evidence_component
        + visual_component
        + hook_component
        + beat_component
        + evidence_pack_component
        + frame_component
    )
    passed = (
        validation_passed
        and evidence_passed
        and visual_passed
        and rights_passed
        and frame_component > 0
        and score >= normalized_threshold
    )
    return SocialQualityReport(
        source_type=normalized_source,
        score=score,
        passed=passed,
        threshold=normalized_threshold,
        frame_mode=bool(frame_mode),
        breakdown={
            "editorial": editorial_component,
            "evidence": evidence_component,
            "visual": visual_component,
            "hook": hook_component,
            "beats": beat_component,
            "evidence_pack": evidence_pack_component,
            "frame_contract": frame_component,
        },
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def summarize_social_quality(report: SocialQualityReport) -> str:
    if report.passed:
        return f"Social quality {report.score}/100 đạt ngưỡng {report.threshold}."
    details = "; ".join(report.reasons + report.warnings)
    return (
        f"Social quality {report.score}/100 dưới ngưỡng {report.threshold}. "
        f"{details or 'Không đủ điều kiện xuất bản.'}"
    )
