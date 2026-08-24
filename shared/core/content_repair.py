"""Điều phối normalize, validate và sửa nội dung tối đa một lần."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from shared.core.content_normalizer import normalize_content
from shared.core.content_validator import (
    ContentValidationReport,
    ValidationIssue,
    validate_content,
)


RepairCallback = Callable[[str], Mapping[str, Any] | None]


@dataclass
class PreparedContent:
    content: dict[str, Any]
    report: ContentValidationReport
    repair_attempts: int = 0
    repaired: bool = False
    initial_report: ContentValidationReport | None = None


def _is_declined(content: Mapping[str, Any]) -> bool:
    return not bool(content.get("topic_fit", True)) or not bool(
        content.get("should_make_video", True)
    )


def _declined_report(content: Mapping[str, Any]) -> ContentValidationReport:
    reason = (
        str(content.get("topic_fit_reason") or content.get("skip_reason") or "")
        .strip()
    )
    message = "AI đã chủ động đánh dấu nội dung không nên sản xuất."
    if reason:
        message = f"{message} {reason}"
    return ContentValidationReport(
        passed=True,
        content_score=0,
        warnings=[
            ValidationIssue(
                code="CONTENT_DECLINED",
                message=message,
                field="should_make_video",
                severity="warning",
            )
        ],
        score_breakdown={
            "hook": 0,
            "evidence": 0,
            "structure": 0,
            "clarity": 0,
            "safety": 0,
            "brand_fit": 0,
        },
        skipped=True,
    )


def build_repair_instruction(
    content: Mapping[str, Any],
    report: ContentValidationReport,
) -> str:
    issues = [
        {
            "code": issue.code,
            "field": issue.field,
            "message": issue.message,
        }
        for issue in report.errors
    ]
    repair_payload = {
        key: value
        for key, value in dict(content).items()
        if key not in {
            "content_validation",
            "content_validation_repaired",
            "content_repair_attempts",
        }
    }
    if repair_payload.get("beats"):
        repair_payload.pop("scenes", None)

    return (
        "\n\n[YÊU CẦU SỬA KỊCH BẢN — CHỈ ĐƯỢC SỬA MỘT LẦN]\n"
        "Kết quả trước chưa qua bộ kiểm định. Hãy sửa đúng các lỗi dưới đây, "
        "không bịa thêm dữ kiện, không đổi bản chất nguồn và không hạ "
        "topic_fit/should_make_video chỉ để né lỗi. Trả về lại TOÀN BỘ JSON "
        "đúng schema, không giải thích ngoài JSON.\n"
        f"LỖI CẦN SỬA:\n{json.dumps(issues, ensure_ascii=False, indent=2)}\n"
        "JSON TRƯỚC:\n"
        f"{json.dumps(repair_payload, ensure_ascii=False, indent=2)}\n"
    )


def _attach_report(
    content: dict[str, Any],
    report: ContentValidationReport,
    *,
    repair_attempts: int,
) -> dict[str, Any]:
    result = dict(content)
    result["content_score"] = report.content_score
    result["content_validation"] = report.to_dict()
    result["content_validation_repaired"] = repair_attempts > 0
    result["content_repair_attempts"] = repair_attempts
    return result


def prepare_content_with_single_repair(
    raw_content: Mapping[str, Any] | None,
    *,
    source_type: str,
    channel_id: str = "",
    source_url: str = "",
    profile: Mapping[str, Any] | None = None,
    repair_callback: RepairCallback | None = None,
) -> PreparedContent:
    """Normalize và validate; gọi repair_callback nhiều nhất một lần."""

    normalized = normalize_content(
        raw_content,
        source_type=source_type,
        channel_id=channel_id,
        source_url=source_url,
    )

    if _is_declined(normalized):
        report = _declined_report(normalized)
        return PreparedContent(
            content=_attach_report(normalized, report, repair_attempts=0),
            report=report,
        )

    initial_report = validate_content(
        normalized,
        source_type=source_type,
        profile=profile,
    )
    if initial_report.passed or repair_callback is None:
        return PreparedContent(
            content=_attach_report(normalized, initial_report, repair_attempts=0),
            report=initial_report,
        )

    repair_instruction = build_repair_instruction(normalized, initial_report)
    try:
        repaired_raw = repair_callback(repair_instruction)
    except Exception:
        repaired_raw = None

    if not repaired_raw:
        return PreparedContent(
            content=_attach_report(normalized, initial_report, repair_attempts=1),
            report=initial_report,
            repair_attempts=1,
            initial_report=initial_report,
        )

    repaired = normalize_content(
        repaired_raw,
        source_type=source_type,
        channel_id=channel_id,
        source_url=source_url,
    )
    if _is_declined(repaired):
        final_report = _declined_report(repaired)
    else:
        final_report = validate_content(
            repaired,
            source_type=source_type,
            profile=profile,
        )

    return PreparedContent(
        content=_attach_report(repaired, final_report, repair_attempts=1),
        report=final_report,
        repair_attempts=1,
        repaired=final_report.passed and not final_report.skipped,
        initial_report=initial_report,
    )


def summarize_validation(report: ContentValidationReport) -> str:
    if report.skipped:
        return "Nội dung được AI đánh dấu bỏ qua."
    if report.passed:
        return f"Content score {report.content_score}/100."
    return "; ".join(
        f"{issue.code}: {issue.message}" for issue in report.errors
    )
