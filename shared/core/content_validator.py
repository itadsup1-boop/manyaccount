"""Kiểm định nội dung bằng luật xác định trước khi tạo TTS."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Mapping

from shared.core.content_models import STORY_TYPES


GENERIC_HOOK_PREFIXES = (
    "có những",
    "đôi khi",
    "không ai ngờ",
    "câu chuyện này",
    "mới đây",
    "được biết",
    "đoạn video này",
    "bài báo này",
    "đang gây xôn xao",
)

GENERIC_CTAS = (
    "theo bạn thì sao",
    "bạn nghĩ sao",
    "hãy để lại bình luận",
    "đừng quên theo dõi",
    "like và follow",
)

SENSITIVE_MOOD = "sensitive_empathy"
HIGH_RISK_EVIDENCE_TERMS = (
    "chứng khoán",
    "đầu tư",
    "điều trị",
    "luật",
    "pháp lý",
    "sức khỏe",
    "tài chính",
    "thuốc",
    "tử vong",
    "y tế",
)


@dataclass
class ValidationIssue:
    code: str
    message: str
    field: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ContentValidationReport:
    passed: bool
    content_score: int
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    score_breakdown: dict[str, int] = field(default_factory=dict)
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "content_score": self.content_score,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "score_breakdown": dict(self.score_breakdown),
            "skipped": self.skipped,
        }


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-ZÀ-ỹ]+", " ", _compact(value).lower()).strip()


def _words(value: Any) -> list[str]:
    return [word for word in _key(value).split() if word]


def _starts_with_generic_hook(hook: str) -> bool:
    key = _key(hook)
    return any(key.startswith(prefix) for prefix in GENERIC_HOOK_PREFIXES)


def _contains_generic_cta(script: str) -> bool:
    key = _key(script)
    return any(phrase in key for phrase in GENERIC_CTAS)


def _hooks_too_similar(first: str, second: str) -> bool:
    first_key = _key(first)
    second_key = _key(second)
    if not first_key or not second_key:
        return False
    return SequenceMatcher(None, first_key, second_key).ratio() >= 0.78


def _estimate_duration_seconds(hook: str, script: str) -> float:
    return len(_words(f"{hook} {script}")) / 3.0


def _profile_duration_range(profile: Mapping[str, Any] | None) -> tuple[int, int] | None:
    value = _compact((profile or {}).get("video_length"))
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if len(numbers) >= 2:
        return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    return None


def validate_content(
    content: Mapping[str, Any],
    *,
    source_type: str,
    profile: Mapping[str, Any] | None = None,
) -> ContentValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    scores = {
        "hook": 25,
        "evidence": 20,
        "structure": 25,
        "clarity": 15,
        "safety": 10,
        "brand_fit": 5,
    }

    def add_error(code: str, message: str, field_name: str, category: str, penalty: int = 8):
        errors.append(ValidationIssue(code, message, field_name, "error"))
        scores[category] = max(0, scores[category] - penalty)

    def add_warning(code: str, message: str, field_name: str, category: str, penalty: int = 3):
        warnings.append(ValidationIssue(code, message, field_name, "warning"))
        scores[category] = max(0, scores[category] - penalty)

    story_type = _compact(content.get("story_type"))
    if story_type not in STORY_TYPES:
        add_error(
            "INVALID_STORY_TYPE",
            "story_type không thuộc danh sách cho phép.",
            "story_type",
            "structure",
        )

    selected_hook = _compact(content.get("selected_hook") or content.get("hook"))
    hook_words = _words(selected_hook)
    variants = [
        item for item in content.get("hook_variants", [])
        if isinstance(item, Mapping) and _compact(item.get("text"))
    ]
    unique_hooks = []
    for item in variants:
        text = _compact(item.get("text"))
        if _key(text) not in {_key(existing) for existing in unique_hooks}:
            unique_hooks.append(text)

    if len(unique_hooks) != 3:
        add_error(
            "HOOK_VARIANTS_INVALID_COUNT",
            "Cần đúng ba hook khác biệt để lựa chọn.",
            "hook_variants",
            "hook",
            10,
        )
    elif any(
        _hooks_too_similar(unique_hooks[i], unique_hooks[j])
        for i in range(len(unique_hooks))
        for j in range(i + 1, len(unique_hooks))
    ):
        add_error(
            "HOOK_VARIANTS_TOO_SIMILAR",
            "Ba hook đang quá giống nhau; cần ba góc result, conflict và impact khác biệt.",
            "hook_variants",
            "hook",
            8,
        )

    required_hook_types = {"result", "conflict", "impact"}
    hook_types = {
        _compact(item.get("hook_type")).lower()
        for item in variants
    }
    if variants and not required_hook_types.issubset(hook_types):
        add_error(
            "HOOK_TYPES_MISSING",
            "Ba hook phải đủ các loại result, conflict và impact.",
            "hook_variants",
            "hook",
            8,
        )
    if any(not _compact(item.get("promise")) for item in variants):
        add_error(
            "HOOK_PROMISE_MISSING",
            "Mỗi hook variant phải có promise mà phần sau sẽ trả lời.",
            "hook_variants",
            "hook",
            6,
        )

    if not selected_hook:
        add_error("HOOK_EMPTY", "Thiếu selected_hook.", "selected_hook", "hook", 12)
    elif len(hook_words) < 5 or len(hook_words) > 20:
        add_error(
            "HOOK_LENGTH_INVALID",
            "Hook phải nằm trong khoảng 5–20 từ.",
            "selected_hook",
            "hook",
        )
    elif len(hook_words) < 8 or len(hook_words) > 15:
        add_warning(
            "HOOK_LENGTH_OUTSIDE_TARGET",
            "Hook nên nằm trong khoảng mục tiêu 8–15 từ.",
            "selected_hook",
            "hook",
        )

    if selected_hook and _starts_with_generic_hook(selected_hook):
        add_error(
            "HOOK_GENERIC",
            "Hook mở đầu chung chung, chưa nêu thẳng sự kiện hoặc tác động.",
            "selected_hook",
            "hook",
        )

    variant_keys = {_key(item) for item in unique_hooks}
    if selected_hook and _key(selected_hook) not in variant_keys:
        add_error(
            "SELECTED_HOOK_NOT_IN_VARIANTS",
            "selected_hook phải trùng chính xác một hook trong hook_variants.",
            "selected_hook",
            "hook",
        )

    if not _compact(content.get("selected_hook_reason")):
        add_error(
            "HOOK_REASON_MISSING",
            "Thiếu lý do chọn hook.",
            "selected_hook_reason",
            "hook",
            5,
        )

    script = _compact(content.get("script_voice"))
    script_words = _words(script)
    if len(script_words) < 25:
        add_error(
            "SCRIPT_TOO_SHORT",
            "script_voice quá ngắn để tạo body và payoff rõ.",
            "script_voice",
            "structure",
            10,
        )
    elif len(script_words) > 150:
        add_error(
            "SCRIPT_TOO_LONG",
            "script_voice quá dài cho video ngắn.",
            "script_voice",
            "structure",
            10,
        )
    elif len(script_words) < 45 or len(script_words) > 110:
        add_warning(
            "SCRIPT_OUTSIDE_TARGET",
            "script_voice nằm ngoài khoảng mục tiêu 45–110 từ.",
            "script_voice",
            "structure",
        )

    if selected_hook and script:
        hook_key = _key(selected_hook)
        script_key = _key(script)
        if script_key.startswith(hook_key) or (
            len(hook_words) >= 5
            and script_key.startswith(" ".join(_words(selected_hook)[:5]))
        ):
            add_error(
                "HOOK_REPEATED_IN_SCRIPT",
                "script_voice đang lặp lại hook ở đầu.",
                "script_voice",
                "clarity",
                10,
            )

    if _contains_generic_cta(script):
        add_error(
            "GENERIC_CTA",
            "Câu chốt/CTA đang chung chung, cần gắn với lựa chọn hoặc chi tiết cụ thể.",
            "script_voice",
            "clarity",
        )

    if not _compact(content.get("main_angle")):
        add_error(
            "MAIN_ANGLE_MISSING",
            "Thiếu main_angle.",
            "main_angle",
            "structure",
        )
    if not _compact(content.get("audience_payoff")):
        add_error(
            "PAYOFF_MISSING",
            "Thiếu audience_payoff để trả lời lý do người xem ở lại.",
            "audience_payoff",
            "structure",
            10,
        )

    evidence = [item for item in content.get("evidence", []) if isinstance(item, Mapping)]
    valid_evidence = [
        item
        for item in evidence
        if _compact(item.get("claim")) and _compact(item.get("source_text"))
    ]
    if not valid_evidence:
        add_error(
            "EVIDENCE_MISSING",
            "Cần ít nhất một evidence có claim và source_text/observed_detail.",
            "evidence",
            "evidence",
            14,
        )
    elif source_type == "article" and len(valid_evidence) < 2:
        add_warning(
            "ARTICLE_EVIDENCE_THIN",
            "Bài báo nên có ít nhất hai bằng chứng cho các ý chính.",
            "evidence",
            "evidence",
        )

    risk_context = _key(" ".join(
        str(value or "")
        for value in (
            content.get("title_tiktok"),
            content.get("main_angle"),
            content.get("risk_flags"),
            (profile or {}).get("topic"),
            (profile or {}).get("niche"),
        )
    ))
    high_risk_evidence = bool(content.get("is_sensitive")) or any(
        _key(term) in risk_context for term in HIGH_RISK_EVIDENCE_TERMS
    )
    reliable_evidence = [
        item
        for item in valid_evidence
        if _compact(item.get("confidence")).lower() != "low"
    ]
    if high_risk_evidence and len(reliable_evidence) < 2:
        add_error(
            "HIGH_RISK_EVIDENCE_THIN",
            "Tin nhạy cảm/rủi ro cao cần ít nhất hai evidence không ở mức low.",
            "evidence",
            "evidence",
            12,
        )

    beats = [item for item in content.get("beats", []) if isinstance(item, Mapping)]
    minimum_beats = 6 if source_type == "article" else 4
    if len(beats) < minimum_beats:
        add_error(
            "BEATS_TOO_FEW",
            (
                f"Cần ít nhất {minimum_beats} beats để có hook, "
                "diễn biến và payoff."
            ),
            "beats",
            "structure",
            12,
        )
    elif len(beats) > 12:
        add_warning(
            "BEATS_TOO_MANY",
            "Có quá nhiều beats; video có thể bị đổi cảnh vụn.",
            "beats",
            "structure",
        )

    if beats:
        if _compact(beats[0].get("role")) != "hook":
            add_error(
                "FIRST_BEAT_NOT_HOOK",
                "Beat đầu tiên phải có role=hook.",
                "beats[0].role",
                "structure",
            )
        if _compact(beats[-1].get("role")) not in {"payoff", "close"}:
            add_error(
                "LAST_BEAT_NOT_PAYOFF",
                "Beat cuối phải có role=payoff hoặc close.",
                "beats[-1].role",
                "structure",
            )
        missing_visual = [
            index + 1
            for index, beat in enumerate(beats)
            if not _compact(beat.get("visual_query"))
        ]
        if missing_visual:
            add_error(
                "BEAT_VISUAL_MISSING",
                f"Beat thiếu visual_query: {missing_visual}.",
                "beats",
                "structure",
                8,
            )
        missing_voice = [
            index + 1
            for index, beat in enumerate(beats)
            if not _compact(beat.get("voice_over"))
        ]
        if missing_voice:
            add_error(
                "BEAT_VOICE_MISSING",
                f"Beat thiếu voice_over: {missing_voice}.",
                "beats",
                "structure",
                8,
            )

    estimated_duration = _estimate_duration_seconds(selected_hook, script)
    duration_range = _profile_duration_range(profile)
    if duration_range:
        minimum, maximum = duration_range
        if estimated_duration < minimum or estimated_duration > maximum:
            add_warning(
                "DURATION_OUTSIDE_PROFILE",
                (
                    f"Thời lượng lời đọc ước tính {estimated_duration:.1f}s, "
                    f"ngoài profile {minimum}–{maximum}s."
                ),
                "script_voice",
                "clarity",
            )

    is_sensitive = bool(content.get("is_sensitive"))
    music_mood = _compact(content.get("music_mood"))
    try:
        music_energy = int(content.get("music_energy", 2))
    except (TypeError, ValueError):
        music_energy = 2
    if is_sensitive and music_mood != SENSITIVE_MOOD:
        add_error(
            "SENSITIVE_MUSIC_INVALID",
            "Nội dung nhạy cảm bắt buộc dùng sensitive_empathy.",
            "music_mood",
            "safety",
            10,
        )
    if is_sensitive and music_energy > 1:
        add_error(
            "SENSITIVE_ENERGY_INVALID",
            "Nội dung nhạy cảm bắt buộc music_energy=1.",
            "music_energy",
            "safety",
            8,
        )

    experiment_id = _compact(content.get("experiment_id"))
    if experiment_id:
        experiment_variant = _compact(content.get("experiment_variant"))
        experiment_variable = _compact(content.get("experiment_variable"))
        experiment_value = _compact(content.get("experiment_value")).lower()
        if not experiment_variant or not experiment_variable or not experiment_value:
            add_error(
                "EXPERIMENT_METADATA_INCOMPLETE",
                "Video thuộc experiment nhưng thiếu variant, variable hoặc value.",
                "experiment_id",
                "structure",
                8,
            )
        selected_variant = next((
            item for item in variants
            if _key(item.get("text")) == _key(selected_hook)
        ), {})
        actual_values = {
            "hook_type": _compact(selected_variant.get("hook_type")).lower(),
            "subtitle_style": _compact(content.get("subtitle_style")).lower(),
            "visual_beat_count": str(len(beats)),
            "cta_mode": _compact(content.get("cta_mode")).lower(),
            "music_energy": str(music_energy),
        }
        if (
            experiment_variable == "subtitle_style"
            and source_type == "facebook"
            and not content.get("have_frame")
        ):
            add_error(
                "EXPERIMENT_NOT_APPLICABLE",
                "Facebook no-frame giữ audio gốc và không render subtitle; "
                "không được tính video này vào subtitle experiment.",
                "have_frame",
                "structure",
                8,
            )
        if experiment_variable == "target_duration_seconds":
            try:
                target_duration = float(experiment_value)
            except (TypeError, ValueError):
                target_duration = 0.0
            if target_duration <= 0 or abs(estimated_duration - target_duration) > 3.0:
                add_error(
                    "EXPERIMENT_VARIANT_MISMATCH",
                    f"Lời đọc ước tính {estimated_duration:.1f}s không khớp nhánh "
                    f"{target_duration:.0f}s (dung sai 3s).",
                    "script_voice",
                    "structure",
                    8,
                )
        elif experiment_variable not in actual_values:
            add_error(
                "EXPERIMENT_VARIABLE_INVALID",
                f"Biến experiment không được hỗ trợ: {experiment_variable}.",
                "experiment_variable",
                "structure",
                8,
            )
        elif actual_values[experiment_variable] != experiment_value:
            add_error(
                "EXPERIMENT_VARIANT_MISMATCH",
                f"Output {experiment_variable}={actual_values[experiment_variable]} "
                f"không khớp nhánh được gán {experiment_value}.",
                experiment_variable,
                "structure",
                8,
            )

    banned_phrases = (profile or {}).get("banned_phrases", [])
    if isinstance(banned_phrases, str):
        banned_phrases = [banned_phrases]
    combined_text = _key(f"{selected_hook} {script}")
    found_banned = [
        _compact(phrase)
        for phrase in banned_phrases
        if _compact(phrase) and _key(phrase) in combined_text
    ]
    if found_banned:
        add_error(
            "BRAND_BANNED_PHRASE",
            f"Nội dung chứa cụm từ bị cấm: {found_banned}.",
            "script_voice",
            "brand_fit",
            5,
        )

    score = max(0, min(100, sum(scores.values())))
    return ContentValidationReport(
        passed=not errors,
        content_score=score,
        errors=errors,
        warnings=warnings,
        score_breakdown=scores,
    )
