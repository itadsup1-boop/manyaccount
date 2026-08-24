"""Evidence checks applied after content normalization and before TTS/render."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


_HIGH_RISK_TERMS = {
    "chung khoan", "dau tu", "dieu tri", "gia vang", "luat", "phap ly",
    "suc khoe", "tai chinh", "thuoc", "tu vong", "y te",
}
_UNCONFIRMED_TERMS = {
    "chua duoc xac nhan", "chua xac nhan", "duoc cho la", "nghi la", "tin don",
}
_CONDITIONAL_TERMS = {
    "can cho xac minh", "chua xac nhan", "co kha nang", "co the", "duoc cho la",
    "neu dung", "theo thong tin ban dau",
}
_ASSERTIVE_TERMS = {"chac chan", "da xac nhan", "khong the phu nhan", "ro rang la"}


def _plain(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _plain(value).split() if len(token) > 2}


def _same_source_url(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return True
    try:
        left = urlsplit(expected)
        right = urlsplit(actual)
        return (
            left.netloc.lower() == right.netloc.lower()
            and left.path.rstrip("/") == right.path.rstrip("/")
        )
    except ValueError:
        return expected == actual


def _supported_by_source(detail: str, source_text: str) -> bool:
    detail_plain = _plain(detail)
    source_plain = _plain(source_text)
    if not detail_plain or not source_plain:
        return False
    if detail_plain in source_plain:
        return True
    detail_tokens = _tokens(detail)
    if not detail_tokens:
        return False
    coverage = len(detail_tokens & _tokens(source_text)) / len(detail_tokens)
    return coverage >= 0.55


@dataclass(frozen=True)
class EvidenceIssue:
    code: str
    message: str
    level: str = "error"


@dataclass(frozen=True)
class EvidenceReport:
    passed: bool
    score: int
    high_risk: bool
    required_evidence_count: int
    valid_evidence_count: int
    errors: tuple[EvidenceIssue, ...]
    warnings: tuple[EvidenceIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def guard_evidence(
    content: Mapping[str, Any],
    *,
    source_type: str = "",
    source_url: str = "",
    source_text: str = "",
    profile: Mapping[str, Any] | None = None,
) -> EvidenceReport:
    """Check provenance, sensitive claims, uncertainty, and visual grounding."""
    errors: list[EvidenceIssue] = []
    warnings: list[EvidenceIssue] = []
    profile = profile or {}
    combined_risk_text = " ".join(
        str(value or "") for value in (
            profile.get("topic"), profile.get("niche"), profile.get("risk_flags"),
            content.get("story_type"), content.get("title"), source_text,
        )
    )
    risk_plain = _plain(combined_risk_text)
    high_risk = bool(content.get("is_sensitive")) or any(
        term in risk_plain for term in _HIGH_RISK_TERMS
    )
    required_count = 2 if high_risk else 1

    evidence_items = content.get("evidence") or []
    if not isinstance(evidence_items, Sequence) or isinstance(evidence_items, (str, bytes)):
        evidence_items = []

    valid_count = 0
    for index, raw_item in enumerate(evidence_items):
        if not isinstance(raw_item, Mapping):
            warnings.append(EvidenceIssue(
                "invalid_evidence_item",
                f"Evidence #{index + 1} không phải object.",
                "warning",
            ))
            continue
        claim = str(raw_item.get("claim") or "").strip()
        detail = str(raw_item.get("source_text") or raw_item.get("detail") or "").strip()
        item_url = str(raw_item.get("source_url") or "").strip()
        confidence = str(raw_item.get("confidence") or "medium").lower()
        if not claim or (not detail and not item_url):
            warnings.append(EvidenceIssue(
                "incomplete_evidence",
                f"Evidence #{index + 1} thiếu claim hoặc nguồn đối chiếu.",
                "warning",
            ))
            continue
        if item_url and source_url and not _same_source_url(source_url, item_url):
            errors.append(EvidenceIssue(
                "source_url_mismatch",
                f"Evidence #{index + 1} trỏ sang URL khác nguồn đang xử lý.",
            ))
            continue
        if source_text and detail and not _supported_by_source(detail, source_text):
            # Video can contain observable facts not present in its short caption.
            if _plain(source_type) == "article":
                errors.append(EvidenceIssue(
                    "unsupported_source_text",
                    f"Evidence #{index + 1} không tìm thấy trong bài nguồn.",
                ))
                continue
            warnings.append(EvidenceIssue(
                "video_evidence_not_text_verified",
                f"Evidence #{index + 1} cần đối chiếu lại với hình/âm thanh video.",
                "warning",
            ))
        if high_risk and confidence == "low":
            warnings.append(EvidenceIssue(
                "low_confidence_sensitive_claim",
                f"Evidence #{index + 1} có độ tin cậy thấp cho chủ đề nhạy cảm.",
                "warning",
            ))
            continue
        valid_count += 1

    if valid_count < required_count:
        errors.append(EvidenceIssue(
            "insufficient_evidence",
            f"Cần ít nhất {required_count} bằng chứng hợp lệ, hiện có {valid_count}.",
        ))

    script = str(content.get("script_voice") or "")
    source_plain = _plain(source_text + " " + " ".join(
        str(item.get("source_text") or "")
        for item in evidence_items if isinstance(item, Mapping)
    ))
    script_plain = _plain(script)
    source_is_unconfirmed = any(term in source_plain for term in _UNCONFIRMED_TERMS)
    script_is_conditional = any(term in script_plain for term in _CONDITIONAL_TERMS)
    if source_is_unconfirmed and not script_is_conditional:
        errors.append(EvidenceIssue(
            "unconfirmed_as_fact",
            "Nguồn chưa xác nhận nhưng lời đọc chưa dùng ngôn ngữ điều kiện.",
        ))
    if any(term in script_plain for term in _ASSERTIVE_TERMS) and valid_count < 2:
        warnings.append(EvidenceIssue(
            "assertion_needs_more_support",
            "Lời khẳng định mạnh cần thêm nguồn/bằng chứng độc lập.",
            "warning",
        ))

    source_tokens = _tokens(source_text)
    if source_tokens:
        beats = content.get("beats") or content.get("visual_beats") or []
        for beat_index, beat in enumerate(beats):
            if not isinstance(beat, Mapping):
                continue
            must_show = beat.get("must_show") or []
            if isinstance(must_show, str):
                must_show = [must_show]
            for visual in must_show:
                visual_tokens = _tokens(visual)
                if visual_tokens and not visual_tokens & source_tokens:
                    warnings.append(EvidenceIssue(
                        "visual_not_grounded",
                        f"Beat #{beat_index + 1} có hình bắt buộc chưa thấy trong nguồn: {visual}",
                        "warning",
                    ))

    score = max(0, 100 - 25 * len(errors) - 6 * len(warnings))
    return EvidenceReport(
        passed=not errors and score >= 65,
        score=score,
        high_risk=high_risk,
        required_evidence_count=required_count,
        valid_evidence_count=valid_count,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def summarize_evidence(report: EvidenceReport) -> str:
    issues = list(report.errors) + list(report.warnings)
    if not issues:
        return f"EvidenceGuard đạt {report.score}/100"
    return "; ".join(issue.message for issue in issues)
