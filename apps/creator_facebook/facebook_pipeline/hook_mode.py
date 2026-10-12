"""Prompt và kiểm định nhẹ cho chế độ Hook rồi phát âm thanh gốc."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from shared.core.content_normalizer import normalize_content
from shared.core.content_repair import PreparedContent
from shared.core.content_validator import ContentValidationReport, ValidationIssue
from shared.core.prompt_builder import build_channel_instruction


def build_hook_prompt(
    *,
    caption: str,
    channel_id: str,
    extra_content: str = "",
    repair_instruction: str = "",
) -> str:
    schema = {
        "schema_version": 1,
        "source_type": "facebook",
        "story_type": "explainer",
        "title_tiktok": "",
        "main_idea": "",
        "hook": "",
        "selected_hook": "",
        "should_make_video": True,
        "topic_fit": True,
        "topic_fit_reason": "",
        "skip_reason": "",
        "tone": "Trung tính",
        "music_mood": "neutral_news",
        "music_energy": 2,
        "is_sensitive": False,
        "quality_score": 7,
        "have_frame": False,
        "script_voice": "",
        "beats": [],
        "risk_flags": [],
    }
    operator_profiles = (extra_content,) if extra_content else ()
    sections = [
        "CHẾ ĐỘ HOOK RỒI GIỮ ÂM THANH VIDEO GỐC — ƯU TIÊN CAO",
        build_channel_instruction(
            channel_id,
            source_type="facebook",
            operator_profiles=operator_profiles,
        ),
        (
            "Xem video và caption để viết đúng MỘT câu hook/title tiếng Việt tự nhiên. "
            "Hook dài 7-16 từ, nêu thẳng chủ thể và sự việc đáng chú ý, có sức hút "
            "nhưng không giật tít sai hoặc bịa dữ kiện. Giọng TTS chỉ đọc câu này ở "
            "đầu video; phần sau dùng nguyên âm thanh nguồn. Vì vậy script_voice và "
            "beats bắt buộc để trống. Không viết bản tin dài, không mô tả tuần tự khung hình."
        ),
        f"CAPTION BÀI VIẾT TRONG NHÓM\n{caption.strip()}",
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


def _fallback_hook(caption: str, maximum_words: int = 16) -> str:
    words = str(caption or "").strip().split()
    return " ".join(words[:maximum_words]).strip(" ,.;:-")


def prepare_hook_content(
    raw_content: Mapping[str, Any] | None,
    *,
    caption: str,
    channel_id: str,
    source_url: str,
) -> PreparedContent:
    raw = dict(raw_content or {})
    hook = str(raw.get("selected_hook") or raw.get("hook") or "").strip()
    if not hook:
        hook = _fallback_hook(caption)
    raw.update(
        {
            "hook": hook,
            "selected_hook": hook,
            "title_tiktok": str(raw.get("title_tiktok") or hook).strip(),
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
    # normalize_content có thể giữ beats từ alias cũ; Mode này tuyệt đối không
    # tạo full script/beat để phản hồi AI ngắn và không sinh TTS body.
    content["script_voice"] = ""
    content["beats"] = []
    content["have_frame"] = False

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    hook_words = _words(content.get("selected_hook") or content.get("hook"))
    if not hook_words:
        errors.append(
            ValidationIssue("HOOK_EMPTY", "Không tạo được hook từ video/caption.", "hook", "error")
        )
    elif len(hook_words) < 5 or len(hook_words) > 20:
        errors.append(
            ValidationIssue(
                "HOOK_LENGTH_INVALID",
                "Hook phải nằm trong khoảng 5-20 từ.",
                "hook",
                "error",
            )
        )
    elif not 7 <= len(hook_words) <= 16:
        warnings.append(
            ValidationIssue(
                "HOOK_OUTSIDE_TARGET",
                "Hook nên nằm trong khoảng 7-16 từ.",
                "hook",
                "warning",
            )
        )
    if not str(content.get("title_tiktok") or "").strip():
        errors.append(
            ValidationIssue("TITLE_EMPTY", "Thiếu title_tiktok.", "title_tiktok", "error")
        )

    score = max(0, 100 - len(errors) * 35 - len(warnings) * 5)
    report = ContentValidationReport(
        passed=not errors,
        content_score=score,
        errors=errors,
        warnings=warnings,
        score_breakdown={
            "hook": 35 if not errors else 0,
            "evidence": 20,
            "structure": 20,
            "clarity": 15,
            "safety": 5,
            "brand_fit": 5,
        },
    )
    content["content_score"] = report.content_score
    content["content_validation"] = report.to_dict()
    content["content_validation_repaired"] = False
    content["content_repair_attempts"] = 0
    return PreparedContent(content=content, report=report)
