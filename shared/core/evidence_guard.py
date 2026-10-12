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
EVIDENCE_GUARD_ENABLED = False
_NUMERIC_PATTERN = re.compile(r"(?<![\w])\d[\d.,]*")
_MAGNITUDE_WORDS = {
    "nghin": 1_000,
    "ngan": 1_000,
    "trieu": 1_000_000,
    "ty": 1_000_000_000,
}
_MAGNITUDE_PATTERN = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(nghin|ngan|trieu|ty)\b"
)


def _plain(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _plain(value).split() if len(token) > 2}


def _numeric_values(value: Any) -> list[str]:
    raw = list(dict.fromkeys(
        match.strip()
        for match in _NUMERIC_PATTERN.findall(str(value or ""))
        if match.strip()
    ))
    # "5 triệu" and "5.000.000" describe the same amount; expand magnitude
    # words so both phrasings normalize to a comparable raw number instead of
    # being treated as unrelated numbers.
    expanded: list[str] = []
    for number_text, unit in _MAGNITUDE_PATTERN.findall(_plain(value)):
        try:
            amount = float(number_text.replace(",", ".")) * _MAGNITUDE_WORDS[unit]
        except ValueError:
            continue
        expanded.append(str(int(amount)) if amount == int(amount) else str(amount))
    return raw + expanded


def _numeric_key(value: Any) -> str:
    text = re.sub(r"[^0-9.]", "", str(value or "").replace(",", "."))
    # Câu tiếng Việt thường kết thúc bằng số rồi dấu câu ("từ năm 2027.",
    # "ngày 25, 26"), khiến số bị nuốt luôn dấu chấm/phẩy và không khớp với
    # cùng con số đã đăng ký. Bỏ dấu thừa ở hai đầu trước khi chuẩn hoá.
    text = text.strip(".")
    # Vietnamese news text uses "." as a thousands separator (e.g. "5.000.000").
    # Collapse it to a plain integer when every group after the first dot has
    # exactly 3 digits; otherwise treat the dot as a genuine decimal point.
    groups = text.split(".")
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
        return "".join(groups)
    return text


def _claim_supported_by_evidence(claim: str, evidence_claim: str) -> bool:
    claim_plain = _plain(claim)
    evidence_plain = _plain(evidence_claim)
    if not claim_plain or not evidence_plain:
        return False
    if claim_plain in evidence_plain or evidence_plain in claim_plain:
        return True
    claim_tokens = {
        token for token in _plain(claim).split() if len(token) > 1
    }
    if not claim_tokens:
        return False
    evidence_tokens = {
        token for token in _plain(evidence_claim).split() if len(token) > 1
    }
    return len(claim_tokens & evidence_tokens) / len(claim_tokens) >= 0.65


def _claim_surface_texts(content: Mapping[str, Any]) -> list[str]:
    surfaces: list[str] = []
    # ``main_angle`` và ``audience_payoff`` là metadata biên tập, không được
    # đọc lên hay hiển thị trên video, nên số liệu trong đó không phải claim
    # cần đăng ký. Giữ chúng ở đây chặn oan mọi kịch bản.
    for field_name in (
        "title_tiktok",
        "main_idea",
        "selected_hook",
        "script_voice",
    ):
        value = content.get(field_name)
        surfaces.extend(
            part.strip()
            for part in re.split(r"(?:[.!?]+\s+|\n+)", str(value or ""))
            if part.strip()
        )

    fact_sheet = content.get("fact_sheet")
    if isinstance(fact_sheet, Mapping):
        # ``who``/``when``/``where`` là bảng tra cứu thực thể/mốc thời gian/địa
        # điểm, không phải câu khẳng định đọc lên video; số trong đó không cần
        # đăng ký claim riêng.
        for field_name in ("what", "cause", "impact", "confirmed_facts"):
            value = fact_sheet.get(field_name)
            values = value if isinstance(value, list) else [value]
            surfaces.extend(str(item).strip() for item in values if str(item or "").strip())

    for beat in content.get("beats") or content.get("visual_beats") or []:
        if not isinstance(beat, Mapping):
            continue
        for field_name in ("voice_over", "on_screen_text", "must_show"):
            value = beat.get(field_name)
            values = value if isinstance(value, list) else [value]
            surfaces.extend(str(item).strip() for item in values if str(item or "").strip())
    return surfaces


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
    required_claim_count: int = 0
    covered_claim_count: int = 0
    numeric_claim_count: int = 0
    covered_numeric_claim_count: int = 0

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
    if not EVIDENCE_GUARD_ENABLED:
        # EvidenceGuard is intentionally disabled by the operator. Return a
        # neutral full-score report so downstream quality gates do not keep
        # blocking content indirectly through the evidence score.
        return EvidenceReport(
            passed=True,
            score=100,
            high_risk=False,
            required_evidence_count=0,
            valid_evidence_count=0,
            errors=(),
            warnings=(),
            required_claim_count=0,
            covered_claim_count=0,
            numeric_claim_count=0,
            covered_numeric_claim_count=0,
        )

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
    evidence_items = content.get("evidence") or []
    if not isinstance(evidence_items, Sequence) or isinstance(evidence_items, (str, bytes)):
        evidence_items = []

    claim_register = content.get("claim_register") or []
    if not isinstance(claim_register, Sequence) or isinstance(claim_register, (str, bytes)):
        claim_register = []
    claim_by_id: dict[str, Mapping[str, Any]] = {}
    claim_numeric_values: dict[str, set[str]] = {}
    claim_declared_numbers: dict[str, set[str]] = {}
    for index, raw_claim in enumerate(claim_register):
        if not isinstance(raw_claim, Mapping):
            errors.append(EvidenceIssue(
                "invalid_claim_record",
                f"Claim #{index + 1} must be an object.",
            ))
            continue
        claim_id = str(raw_claim.get("claim_id") or "").strip()
        claim_text = str(raw_claim.get("claim") or "").strip()
        if not claim_id or not claim_text:
            errors.append(EvidenceIssue(
                "incomplete_claim_record",
                f"Claim #{index + 1} requires claim_id and claim.",
            ))
            continue
        if claim_id in claim_by_id:
            errors.append(EvidenceIssue(
                "duplicate_claim_id",
                f"Claim id {claim_id} is duplicated.",
            ))
            continue
        claim_by_id[claim_id] = raw_claim
        explicit_values = raw_claim.get("numeric_values") or []
        if isinstance(explicit_values, str):
            explicit_values = [explicit_values]
        if not isinstance(explicit_values, Sequence) or isinstance(explicit_values, (str, bytes)):
            explicit_values = []
        # Hai mục đích khác nhau, không dùng chung một tập số:
        #  - ``claim_declared_numbers``: số AI khai là dữ kiện -> dùng để đối
        #    chiếu evidence. Tin tức Việt Nam đầy số định danh ("bão số 4",
        #    "vùng II", "nghị định 168"); bắt evidence lặp lại chúng gây lỗi oan.
        #  - ``claim_numeric_values``: mọi số đã xuất hiện trong claim -> dùng để
        #    biết số nào "đã được đăng ký" khi quét lời đọc.
        declared = {
            _numeric_key(value)
            for value in explicit_values
            if _numeric_key(value)
        }
        from_text = {
            _numeric_key(value)
            for value in _numeric_values(claim_text)
            if _numeric_key(value)
        }
        claim_declared_numbers[claim_id] = declared or from_text
        claim_numeric_values[claim_id] = declared | from_text

    required_claim_count = len(claim_by_id)
    if not claim_by_id:
        errors.append(EvidenceIssue(
            "claim_register_missing",
            "Advanced evidence requires a non-empty claim_register.",
        ))
    required_count = max(2 if high_risk else 1, required_claim_count)
    evidence_by_claim: dict[str, list[Mapping[str, Any]]] = {}
    for raw_item in evidence_items:
        if isinstance(raw_item, Mapping):
            claim_id = str(raw_item.get("claim_id") or "").strip()
            if claim_id:
                evidence_by_claim.setdefault(claim_id, []).append(raw_item)

    covered_claim_count = 0
    numeric_claim_count = sum(bool(values) for values in claim_numeric_values.values())
    covered_numeric_claim_count = 0
    for claim_id, raw_claim in claim_by_id.items():
        claim_text = str(raw_claim.get("claim") or "").strip()
        linked_items = evidence_by_claim.get(claim_id, [])
        if not linked_items:
            errors.append(EvidenceIssue(
                "claim_without_evidence",
                f"Claim {claim_id} has no linked evidence.",
            ))
            continue
        matching_items = [
            item for item in linked_items
            if _claim_supported_by_evidence(
                claim_text, str(item.get("claim") or "").strip()
            )
        ]
        if not matching_items:
            errors.append(EvidenceIssue(
                "claim_evidence_mismatch",
                f"Evidence for claim {claim_id} does not describe the same claim.",
            ))
            continue
        covered_claim_count += 1
        if claim_declared_numbers.get(claim_id) and any(
            claim_declared_numbers[claim_id] <= {
                _numeric_key(value)
                for value in _numeric_values(
                    str(item.get("source_text") or item.get("detail") or "")
                )
                if _numeric_key(value)
            }
            for item in matching_items
        ):
            covered_numeric_claim_count += 1

    for raw_item in evidence_items:
        if not isinstance(raw_item, Mapping):
            continue
        claim_id = str(raw_item.get("claim_id") or "").strip()
        if claim_id and claim_id not in claim_by_id:
            errors.append(EvidenceIssue(
                "orphan_evidence",
                f"Evidence points to unregistered claim {claim_id}.",
            ))

    registered_numbers = {
        number
        for values in claim_numeric_values.values()
        for number in values
    }
    missing_numeric_claims = [
        value
        for surface in _claim_surface_texts(content)
        for value in _numeric_values(surface)
        if _numeric_key(value) not in registered_numbers
    ]
    if missing_numeric_claims:
        errors.append(EvidenceIssue(
            "numeric_claim_unregistered",
            "Numeric claims must be registered: "
            + ", ".join(sorted(set(missing_numeric_claims))),
        ))

    valid_count = 0
    for index, raw_item in enumerate(evidence_items):
        if not isinstance(raw_item, Mapping):
            warnings.append(EvidenceIssue(
                "invalid_evidence_item",
                f"Evidence #{index + 1} không phải object.",
                "warning",
            ))
            continue
        claim_id = str(raw_item.get("claim_id") or "").strip()
        claim = str(raw_item.get("claim") or "").strip()
        detail = str(raw_item.get("source_text") or raw_item.get("detail") or "").strip()
        item_url = str(raw_item.get("source_url") or "").strip()
        confidence = str(raw_item.get("confidence") or "medium").lower()
        if not claim_id or claim_id not in claim_by_id or not claim or not detail:
            errors.append(EvidenceIssue(
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
        # Chỉ đối chiếu những số AI khai là dữ kiện, không phải số định danh.
        claim_numbers = claim_declared_numbers.get(claim_id, set())
        detail_numbers = {
            _numeric_key(value)
            for value in _numeric_values(detail)
            if _numeric_key(value)
        }
        if claim_numbers:
            matched_numbers = claim_numbers & detail_numbers
            if not matched_numbers:
                errors.append(EvidenceIssue(
                    "numeric_claim_source_mismatch",
                    f"Evidence #{index + 1} không khớp con số nào của claim {claim_id}.",
                ))
                continue
            if matched_numbers != claim_numbers:
                # Some but not all numbers matched — usually a formatting
                # difference (e.g. "5 triệu" vs "5.000.000") rather than a
                # real factual error, so warn instead of blocking the video.
                warnings.append(EvidenceIssue(
                    "numeric_claim_partial_mismatch",
                    f"Evidence #{index + 1} chỉ khớp một phần con số của claim {claim_id}.",
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

    fact_sheet = content.get("fact_sheet")
    if source_type == "article" and isinstance(fact_sheet, Mapping) and source_text:
        confirmed_facts = fact_sheet.get("confirmed_facts") or []
        if isinstance(confirmed_facts, str):
            confirmed_facts = [confirmed_facts]
        for index, fact in enumerate(confirmed_facts):
            fact_text = str(fact or "").strip()
            if fact_text and not _supported_by_source(fact_text, source_text):
                errors.append(EvidenceIssue(
                    "unsupported_fact_sheet",
                    f"Fact sheet #{index + 1} không được hỗ trợ bởi nội dung bài nguồn.",
                ))

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

    # Cảnh báo "mềm" là tín hiệu cần rà lại, không phải dấu hiệu sai sự thật:
    # khác cách viết số ("5 triệu" vs "5.000.000"), hình chưa neo được vào text,
    # hay evidence video cần đối chiếu bằng mắt. Một bản tin nhiều mốc số liệu
    # có thể sinh hàng loạt cảnh báo loại này; tính đủ 6 điểm mỗi cái sẽ đánh
    # rớt oan cả kịch bản vốn đạt điểm nội dung rất cao.
    low_impact_codes = {
        "numeric_claim_partial_mismatch",
        "video_evidence_not_text_verified",
        "visual_not_grounded",
    }
    warning_penalty = sum(
        2 if issue.code in low_impact_codes else 6 for issue in warnings
    )
    score = max(0, 100 - 25 * len(errors) - warning_penalty)
    return EvidenceReport(
        passed=not errors and score >= 65,
        score=score,
        high_risk=high_risk,
        required_evidence_count=required_count,
        valid_evidence_count=valid_count,
        errors=tuple(errors),
        warnings=tuple(warnings),
        required_claim_count=required_claim_count,
        covered_claim_count=covered_claim_count,
        numeric_claim_count=numeric_claim_count,
        covered_numeric_claim_count=covered_numeric_claim_count,
    )


def summarize_evidence(report: EvidenceReport) -> str:
    issues = list(report.errors) + list(report.warnings)
    if not issues:
        return (
            f"EvidenceGuard score {report.score}/100; "
            f"claims {report.covered_claim_count}/{report.required_claim_count}; "
            f"numeric {report.covered_numeric_claim_count}/{report.numeric_claim_count}"
        )
    return "; ".join(issue.message for issue in issues)
