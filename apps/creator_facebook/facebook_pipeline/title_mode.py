"""Prompt và kiểm định nhẹ cho chế độ chỉ viết lại tiêu đề."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from shared.core.content_normalizer import normalize_content
from shared.core.content_repair import PreparedContent
from shared.core.content_validator import ContentValidationReport, ValidationIssue
from shared.core.prompt_builder import build_channel_instruction


def build_title_only_prompt(
    *,
    caption: str,
    channel_id: str,
    extra_content: str = "",
    repair_instruction: str = "",
) -> str:
    schema = {
        "schema_version": 1,
        "source_type": "facebook",
        "story_type": "news",
        "title_tiktok": "",
        "hook": "",
        "should_make_video": True,
        "topic_fit": True,
        "topic_fit_reason": "",
        "skip_reason": "",
        "tone": "Trung tính",
        "is_sensitive": False,
        "quality_score": 7,
        "have_frame": False,
        "script_voice": "",
        "beats": [],
        "risk_flags": [],
    }
    operator_profiles = (extra_content,) if extra_content else ()
    sections = [
        "CHẾ ĐỘ CHỈ VIẾT LẠI TIÊU ĐỀ — GIỮ NGUYÊN TOÀN BỘ VIDEO GỐC",
        build_channel_instruction(
            channel_id,
            source_type="facebook",
            operator_profiles=operator_profiles,
        ),
        (
            "Xem video và caption để viết lại DUY NHẤT tiêu đề đăng TikTok "
            "(title_tiktok) tiếng Việt tự nhiên, dài 8-16 từ, nêu thẳng chủ thể "
            "và sự việc đáng chú ý, có sức hút nhưng tuyệt đối không giật tít "
            "sai hoặc bịa dữ kiện. Tiêu đề này vừa dùng làm intro voice mở đầu "
            "vừa làm caption; thân video gốc giữ nguyên nên script_voice, beats "
            "bắt buộc để trống; have_frame bắt buộc false. Trường hook có thể "
            "để trùng title_tiktok. Không viết bản tin, không mô tả tuần tự "
            "khung hình."
        ),
        f"CAPTION/TIÊU ĐỀ GỐC\n{caption.strip()}",
    ]
    if repair_instruction.strip():
        sections.append(f"YÊU CẦU SỬA\n{repair_instruction.strip()}")
    sections.append(
        "Chỉ trả JSON thuần đúng cấu trúc sau:\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
    )
    sections.append("chỉ được trả về text json")
    return "\n\n".join(section for section in sections if section)


def _words(text: Any) -> list[str]:
    return re.findall(r"[0-9A-Za-zÀ-ỹ]+", str(text or ""))


def prepare_title_only_content(
    raw_content: Mapping[str, Any] | None,
    *,
    caption: str,
    channel_id: str,
    source_url: str,
) -> PreparedContent:
    raw = dict(raw_content or {})
    title = str(raw.get("title_tiktok") or "").strip()
    if not title:
        words = str(caption or "").strip().split()
        title = " ".join(words[:16]).strip(" ,.;:-")
    hook = str(raw.get("hook") or "").strip() or title
    raw.update(
        {
            "title_tiktok": title,
            "hook": hook,
            "selected_hook": hook,
            "script_voice": "",
            "beats": [],
            "have_frame": False,
        }
    )
    content = normalize_content(
        raw,
        source_type="facebook",
        channel_id=channel_id,
        source_url=source_url,
    )
    content["script_voice"] = ""
    content["beats"] = []
    content["have_frame"] = False

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    title_words = _words(content.get("title_tiktok"))
    if not title_words:
        errors.append(
            ValidationIssue("TITLE_EMPTY", "Không tạo được tiêu đề từ video/caption.", "title_tiktok", "error")
        )
    elif not 5 <= len(title_words) <= 24:
        warnings.append(
            ValidationIssue(
                "TITLE_OUTSIDE_TARGET",
                "Tiêu đề nên nằm trong khoảng 5-24 từ.",
                "title_tiktok",
                "warning",
            )
        )

    score = max(0, 100 - len(errors) * 40 - len(warnings) * 5)
    report = ContentValidationReport(
        passed=not errors,
        content_score=score,
        errors=errors,
        warnings=warnings,
        score_breakdown={
            "title": 50 if not errors else 0,
            "evidence": 20,
            "safety": 15,
            "brand_fit": 15,
        },
    )
    content["content_score"] = report.content_score
    content["content_validation"] = report.to_dict()
    content["content_validation_repaired"] = False
    content["content_repair_attempts"] = 0
    return PreparedContent(content=content, report=report)
