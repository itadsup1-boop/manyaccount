"""Hợp nhất hồ sơ kênh, ngữ cảnh thương hiệu và hợp đồng output AI."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any, Iterable, Mapping

from shared.core.channel_editorial import (
    TARGET_VIDEO_DURATION_SECONDS,
    TARGET_VOICE_SPEED,
    load_channel_editorial,
)
from shared.core.evidence_guard import EVIDENCE_GUARD_ENABLED


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET_VIDEO_LENGTH = (
    "50-55 giây; tổng hook và script khoảng 150-165 từ; "
    "hook 10-16 từ và script_voice khoảng 140-150 từ."
)

NEWSROOM_SCRIPT_STANDARD = """QUY CHUẨN LỜI DẪN BẢN TIN — ƯU TIÊN CAO
- Viết như một biên tập viên đang dẫn bản tin hiện đại, không viết như người đang xem và mô tả từng khung hình.
- Mục tiêu 50-55 giây: hook 10-16 từ, script_voice 140-150 từ. Quy chuẩn này ưu tiên hơn mọi mô tả thời lượng cũ còn sót trong hồ sơ kênh.
- Hình ảnh chỉ là bằng chứng hỗ trợ. Tối đa 20% lời thoại dùng để tả chi tiết nhìn thấy; không kể tuần tự máy quay, góc quay hoặc cảnh tiếp theo.
- Không lặp các cách dẫn như “video cho thấy”, “phần mô tả”, “hình ảnh cho thấy”, “máy quay”, “góc quay”, “xuất hiện”. Nếu dữ kiện chỉ có trong caption, ghi nguồn một lần thật tự nhiên rồi tiếp tục dẫn tin.
- Mạch lời bắt buộc: sự kiện chính → bối cảnh cần thiết → diễn biến hoặc dữ kiện nổi bật → ý nghĩa/tác động → payoff và câu chốt.
- Dùng động từ cụ thể, từ nối tự nhiên và nhịp câu dài-ngắn xen kẽ. Giọng có cảm xúc phù hợp sự kiện nhưng không cường điệu, phán xét hoặc bịa thêm.
- Mỗi câu phải làm câu chuyện tiến lên. Không dùng nhiều câu để diễn đạt lại cùng một hình ảnh hay cùng một ý.
- Nếu nguồn không đủ dữ kiện cho một bản tin 50 giây an toàn, đặt should_make_video=false; không kéo dài bằng mô tả khung hình hoặc suy đoán."""
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
except Exception:
    pass

PROFILE_FIELD_LABELS = (
    ("Tên kênh", "channel_name"),
    ("Chủ đề chính", "topic"),
    ("Tệp người xem", "audience"),
    ("Lời hứa nội dung", "content_promise"),
    ("Mục tiêu chính", "primary_goal"),
    ("Voice ổn định", "brand_voice"),
    ("Tone mặc định", "tone_style"),
    ("Tone theo ngữ cảnh", "tone_by_context"),
    ("Nỗi đau/nhu cầu người xem", "audience_pains"),
    ("Trụ cột nội dung", "content_pillars"),
    ("Story type được phép", "allowed_story_types"),
    ("Hook ưu tiên", "preferred_hook_types"),
    ("Độ dài video", "video_length"),
    ("Format lặp lại", "format_style"),
    ("Kiểu hook phù hợp", "hook_style"),
    ("Ưu tiên chọn nguồn/video", "source_preference"),
    ("Cách kéo bình luận", "comment_strategy"),
    ("CTA phù hợp", "cta_styles"),
    ("Chuẩn bằng chứng", "evidence_standard"),
    ("Cụm từ cấm", "banned_phrases"),
    ("Điều cần tránh", "avoid"),
    ("Preset hình ảnh", "video_style"),
    ("Ví dụ hiệu quả", "winning_examples"),
    ("Ví dụ thất bại", "losing_examples"),
    ("Chỉ đạo tùy biến", "custom_instruction"),
)

CONTENT_PROFILE_FIELDS = tuple(key for _label, key in PROFILE_FIELD_LABELS)
OPERATOR_PROFILE_FIELDS = (
    "channel_name",
    "topic",
    "audience",
    "content_promise",
    "primary_goal",
    "tone_style",
    "video_length",
    "format_style",
    "hook_style",
    "source_preference",
    "comment_strategy",
    "avoid",
    "winning_examples",
    "custom_instruction",
)

DEFAULT_CONTENT_PROFILE: dict[str, Any] = {
    "channel_name": "",
    "topic": "",
    "audience": "",
    "content_promise": "Mỗi video phải đem lại một thông tin hoặc payoff rõ.",
    "primary_goal": "retention",
    "brand_voice": ["Rõ ràng", "Cụ thể", "Đáng tin"],
    "tone_style": "Tự nhiên, câu ngắn, không lên gân hoặc giật tít sai sự thật.",
    "tone_by_context": {},
    "audience_pains": [],
    "content_pillars": [],
    "allowed_story_types": [
        "breaking_update",
        "warning",
        "explainer",
        "conflict",
        "human_story",
        "achievement",
        "comparison",
        "sports_moment",
        "entertainment_drama",
    ],
    "preferred_hook_types": ["result", "conflict", "impact"],
    "video_length": TARGET_VIDEO_LENGTH,
    "format_style": "Hook cụ thể, bối cảnh ngắn, bằng chứng, tác động và payoff.",
    "hook_style": "Nêu thẳng chủ thể và sự việc trong hai giây đầu.",
    "source_preference": "Ưu tiên nguồn có chủ thể, hành động và dữ kiện kiểm chứng được.",
    "comment_strategy": "Chỉ hỏi điều gắn trực tiếp với lựa chọn hoặc chi tiết trong nội dung.",
    "cta_styles": [],
    "evidence_standard": "strict",
    "banned_phrases": ["Mới đây", "Được biết", "Đang gây xôn xao"],
    "avoid": "Không bịa, suy đoán thành sự thật hoặc dùng CTA chung chung.",
    "video_style": {},
    "winning_examples": [],
    "losing_examples": [],
    "custom_instruction": "",
}


def _clean_channel_id(channel_id: str) -> str:
    return str(channel_id or "").replace("@", "").strip()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalize_content_profile(
    profile: Any,
    *,
    include_defaults: bool = True,
) -> dict[str, Any]:
    """Chuẩn hóa profile cũ dạng chuỗi/dict mà không làm mất field có cấu trúc."""
    normalized = deepcopy(DEFAULT_CONTENT_PROFILE) if include_defaults else {}
    if isinstance(profile, str):
        if profile.strip():
            normalized["custom_instruction"] = profile.strip()
        return normalized
    if not isinstance(profile, Mapping):
        return normalized

    for key in CONTENT_PROFILE_FIELDS:
        value = profile.get(key)
        if value is not None:
            normalized[key] = deepcopy(value)
    return normalized


def merge_content_profiles(*profiles: Any) -> dict[str, Any]:
    """Trộn profile theo thứ tự; profile sau là override có chủ đích của operator."""
    merged = deepcopy(DEFAULT_CONTENT_PROFILE)
    for profile in profiles:
        normalized = normalize_content_profile(profile, include_defaults=False)
        for key, value in normalized.items():
            if _has_value(value):
                merged[key] = deepcopy(value)
    return merged


def _merge_profile_overrides(*profiles: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for profile in profiles:
        normalized = normalize_content_profile(profile, include_defaults=False)
        for key, value in normalized.items():
            if _has_value(value):
                merged[key] = deepcopy(value)
    return merged


def load_runtime_content_profile(channel_id: str) -> dict[str, Any]:
    """Đọc override legacy, tách biệt khỏi nguồn định vị biên tập trung tâm."""
    clean_id = _clean_channel_id(channel_id)
    if not clean_id:
        return {}

    synced_profile: Any = {}
    try:
        from shared.services.supabase_api import SupabaseAPI

        synced_profiles = SupabaseAPI.get_tiktok_content_profiles()
        synced_profile = synced_profiles.get(clean_id, {})
    except Exception:
        synced_profile = {}

    local_profile: Any = {}
    config_path = os.path.join(
        PROJECT_ROOT,
        "assets",
        "channels",
        clean_id,
        "config.json",
    )
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
            local_profile = config.get("content_profile", {})
        except Exception:
            local_profile = {}

    return _merge_profile_overrides(synced_profile, local_profile)


def get_content_profile(
    channel_id: str,
    *operator_profiles: Any,
    include_runtime: bool = True,
) -> dict[str, Any]:
    """Lấy profile trung tâm rồi áp dụng override runtime/operator để tương thích."""
    editorial_profile = load_channel_editorial(channel_id).get("content_profile", {})
    profiles: list[Any] = [editorial_profile]
    if include_runtime:
        profiles.append(load_runtime_content_profile(channel_id))
    profiles.extend(operator_profiles)
    merged = merge_content_profiles(*profiles)
    # Chính sách thời lượng chung có độ ưu tiên cao nhất để Supabase/profile
    # cũ không tiếp tục yêu cầu video 20-30 hoặc 45-60 giây.
    merged["video_length"] = TARGET_VIDEO_LENGTH
    return merged


def extract_operator_overrides(channel_id: str, profile: Any) -> dict[str, Any]:
    """Chỉ lưu field operator thật sự đổi, không sao chép profile trung tâm."""
    submitted = normalize_content_profile(profile, include_defaults=False)
    central = get_content_profile(channel_id, include_runtime=False)
    return {
        key: deepcopy(submitted[key])
        for key in OPERATOR_PROFILE_FIELDS
        if key in submitted
        and _has_value(submitted[key])
        and submitted[key] != central.get(key)
    }


def _format_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return "; ".join(
            f"{key}: {_format_value(item)}"
            for key, item in value.items()
            if _has_value(item)
        )
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_format_value(item) for item in value if _has_value(item))
    return str(value or "").strip()


def format_content_profile(profile: Mapping[str, Any]) -> str:
    lines = []
    for label, key in PROFILE_FIELD_LABELS:
        value = _format_value(profile.get(key))
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _context_keys(
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> Iterable[str]:
    if is_sensitive:
        yield "sensitive"
    tone_key = str(tone or "").strip().lower()
    tone_aliases = {
        "đồng cảm": "sensitive",
        "cảnh báo": "warning",
        "tích cực": "positive",
        "trung tính": "neutral",
    }
    if tone_key in tone_aliases:
        yield tone_aliases[tone_key]
    if story_type:
        yield str(story_type).strip()
    yield "default"


def _tone_from_profile(
    profile: Mapping[str, Any],
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> str:
    presets = profile.get("tone_by_context", {})
    if not isinstance(presets, Mapping):
        return str(profile.get("tone_style", "")).strip()
    for key in _context_keys(story_type, tone, is_sensitive):
        value = presets.get(key)
        if _has_value(value):
            return _format_value(value)
    return str(profile.get("tone_style", "")).strip()


def get_tone_preset(
    channel_id: str,
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> str:
    return _tone_from_profile(
        get_content_profile(channel_id),
        story_type=story_type,
        tone=tone,
        is_sensitive=is_sensitive,
    )


def _voice_from_editorial(
    editorial: Mapping[str, Any],
    *,
    direction: str,
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> dict[str, Any]:
    presets = editorial.get("voice_presets", {})
    if not isinstance(presets, Mapping):
        presets = {}

    selected: dict[str, Any] = {}
    for key in _context_keys(story_type, tone, is_sensitive):
        candidate = presets.get(key)
        if isinstance(candidate, Mapping):
            selected = dict(candidate)
            break
    selected["speed"] = TARGET_VOICE_SPEED
    selected.setdefault("direction", direction)
    return selected


def get_voice_preset(
    channel_id: str,
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> dict[str, Any]:
    editorial = load_channel_editorial(channel_id)
    central_profile = merge_content_profiles(editorial.get("content_profile", {}))
    direction = _tone_from_profile(
        central_profile,
        story_type=story_type,
        tone=tone,
        is_sensitive=is_sensitive,
    )
    return _voice_from_editorial(
        editorial,
        direction=direction,
        story_type=story_type,
        tone=tone,
        is_sensitive=is_sensitive,
    )


def get_video_style(channel_id: str) -> dict[str, Any]:
    style = get_content_profile(channel_id).get("video_style", {})
    return deepcopy(style) if isinstance(style, Mapping) else {}


def build_output_schema(
    source_type: str = "video",
    experiment_assignment: Mapping[str, Any] | None = None,
) -> str:
    """Sinh hợp đồng JSON dùng chung cho Article, Facebook và TikTok Matrix."""
    is_video = source_type in {"video", "facebook", "tiktok"}
    schema: dict[str, Any] = {
        "schema_version": 1,
        "content_id": "",
        "channel_id": "",
        "source_type": source_type,
        "source_url": "",
        "story_type": "explainer",
        "title_tiktok": "",
        "main_idea": "",
        "main_angle": "",
        "audience_payoff": "",
        "hook_variants": [
            {"text": "", "hook_type": "result", "promise": "", "score": 0},
            {"text": "", "hook_type": "conflict", "promise": "", "score": 0},
            {"text": "", "hook_type": "impact", "promise": "", "score": 0},
        ],
        "selected_hook": "",
        "selected_hook_reason": "",
        "hook": "",
        "script_voice": "",
        "curiosity_point": "",
        "viewer_emotion": "",
        "should_make_video": True,
        "tone": "Trung tính",
        "music_mood": "neutral_news",
        "music_energy": 2,
        "subtitle_style": "keyword_highlight",
        "cta_mode": "specific",
        "target_duration_seconds": TARGET_VIDEO_DURATION_SECONDS,
        "visual_beat_count": 0,
        "experiment_id": "",
        "experiment_variant": "",
        "experiment_variable": "",
        "experiment_value": "",
        "is_sensitive": False,
        "music_reason": "",
        "topic_fit": True,
        "topic_fit_reason": "",
        "quality_score": 7,
        "skip_reason": "",
        "claim_register": [
            {
                "claim_id": "claim_1",
                "claim": "",
                "claim_type": "fact",
                "numeric_values": [],
            }
        ] if EVIDENCE_GUARD_ENABLED else [],
        "evidence": [
            {
                "claim_id": "claim_1",
                "claim": "",
                "claim_type": "fact",
                "numeric_values": [],
                "source_text": "",
                "source_url": "",
                "confidence": "high",
            }
        ] if EVIDENCE_GUARD_ENABLED else [],
        "beats": [
            {
                "beat_number": 1,
                "role": "hook",
                "duration_hint": 2.0,
                "voice_over": "",
                "visual_query": "",
                "on_screen_text": "",
                "motion": "slow_push_in",
                "transition": "cut",
                "sfx": "",
                "must_show": [],
            }
        ],
        "retention_risks": [],
        "risk_flags": [],
    }
    if is_video:
        schema["have_frame"] = False
        schema["detected_competitor_frame_end_sec"] = None
    if source_type == "article":
        schema["fact_sheet"] = {
            "who": [],
            "what": "",
            "when": "",
            "where": "",
            "cause": "",
            "impact": "",
            "confirmed_facts": [],
            "unknowns": [],
        }
    if experiment_assignment:
        for key in (
            "experiment_id", "experiment_variant", "experiment_variable",
            "experiment_value",
        ):
            schema[key] = experiment_assignment.get(key, "")
        variable = str(experiment_assignment.get("experiment_variable") or "")
        if variable in schema:
            schema[variable] = experiment_assignment.get("experiment_value")
    return json.dumps(schema, ensure_ascii=False, indent=2)


def resolve_prompt_experiment(
    channel_id: str,
    *,
    source_type: str,
    content_key: str = "",
    task_input: str = "",
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Resolve the active arm once so callers can also stamp the AI result."""
    stable_key = str(content_key or "").strip()
    if not stable_key and str(task_input or "").strip():
        stable_key = hashlib.sha256(
            str(task_input).strip().encode("utf-8")
        ).hexdigest()
    if not stable_key:
        return None
    from shared.core.experiment_manager import resolve_experiment_assignment

    return resolve_experiment_assignment(
        channel_id,
        stable_key,
        source_type=source_type,
        enabled=enabled,
    )


def build_channel_instruction(
    channel_id: str,
    *,
    source_type: str = "video",
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
    operator_profiles: Iterable[Any] = (),
) -> str:
    profile = get_content_profile(channel_id, *operator_profiles)
    contextual_tone = _tone_from_profile(
        profile,
        story_type=story_type,
        tone=tone,
        is_sensitive=is_sensitive,
    )
    voice_preset = _voice_from_editorial(
        load_channel_editorial(channel_id),
        direction=contextual_tone,
        story_type=story_type,
        tone=tone,
        is_sensitive=is_sensitive,
    )
    return (
        "HỒ SƠ KÊNH BẮT BUỘC\n"
        f"- Loại nguồn: {source_type}\n"
        f"{format_content_profile(profile)}\n"
        f"- Tone được chọn cho ngữ cảnh: {contextual_tone}\n"
        f"- Hướng dẫn giọng đọc: {_format_value(voice_preset)}"
    ).strip()


def build_prompt(
    base_prompt: str,
    channel_id: str,
    *,
    source_type: str,
    task_input: str = "",
    repair_instruction: str = "",
    operator_profiles: Iterable[Any] = (),
    performance_lessons: Any = None,
    experiment_assignment: Mapping[str, Any] | None = None,
    experiment_content_key: str = "",
    include_output_schema: bool = True,
) -> str:
    """Ghép prompt theo cùng một thứ tự ưu tiên cho mọi pipeline."""
    sections = [
        str(base_prompt or "").strip(),
        build_channel_instruction(
            channel_id,
            source_type=source_type,
            operator_profiles=operator_profiles,
        ),
        NEWSROOM_SCRIPT_STANDARD,
    ]
    tiktok_topic_gate_enabled = str(
        os.environ.get("TIKTOK_TOPIC_GATE", "off")
    ).strip().lower() in {"1", "true", "yes", "on"}
    if source_type == "tiktok" and not tiktok_topic_gate_enabled:
        sections.append(
            "DUYỆT NGUỒN TIKTOK BỞI OPERATOR\n"
            "Nguồn TikTok đã được operator kiểm tra và duyệt trước khi đưa vào pipeline. "
            "Không được từ chối video chỉ vì lệch topic/định vị của kênh đầu ra; hãy đặt "
            "topic_fit=true và tiếp tục viết theo đúng hình ảnh, âm thanh, caption thực tế. "
            "Chỉ đặt should_make_video=false khi thiếu file video, không đọc được hình/âm thanh, "
            "thiếu bằng chứng nghiêm trọng hoặc nội dung không thể dựng an toàn."
        )
    assignment = experiment_assignment
    if assignment is None:
        assignment = resolve_prompt_experiment(
            channel_id,
            source_type=source_type,
            content_key=experiment_content_key,
            task_input=task_input,
        )
    if assignment:
        from shared.core.experiment_manager import experiment_instruction

        sections.append(
            "THỬ NGHIỆM A/B — CHỈ ĐỔI MỘT BIẾN\n"
            f"- experiment_id: {assignment.get('experiment_id', '')}\n"
            f"- variant: {assignment.get('experiment_variant', '')}\n"
            f"- biến duy nhất: {assignment.get('experiment_variable', '')}="
            f"{assignment.get('experiment_value', '')}\n"
            f"- Cách áp dụng: {experiment_instruction(assignment)}\n"
            "Giữ nguyên mọi thuộc tính ngoài biến trên và chép nguyên bốn field "
            "experiment_* vào JSON output."
        )

    resolved_lessons = performance_lessons
    if resolved_lessons is None:
        from shared.core.channel_learning import load_prompt_learning

        resolved_lessons = load_prompt_learning(channel_id)
    lessons = _format_value(resolved_lessons)
    if lessons:
        sections.append(
            "BÀI HỌC HIỆU SUẤT ĐÃ ĐỦ MẪU\n"
            f"{lessons}\n"
            "Chỉ dùng để ưu tiên cách thể hiện; không được thay thế dữ kiện nguồn."
        )
    if EVIDENCE_GUARD_ENABLED:
        sections.append(
            "ADVANCED EVIDENCE CONTRACT\n"
            "Register every factual claim in claim_register with a unique claim_id, claim_type, "
            "and numeric_values. Every claim_id must have at least one evidence item with the "
            "same claim_id, matching claim text, and source_text/observed_detail. Every number "
            "in a claim, script, hook, title, fact sheet, or on-screen text must be registered "
            "and reproduced in the evidence source_text. Do not invent or estimate numbers."
        )
    if task_input.strip():
        sections.append(f"ĐẦU VÀO TÁC VỤ\n{task_input.strip()}")
    if repair_instruction.strip():
        sections.append(f"YÊU CẦU SỬA DUY NHẤT\n{repair_instruction.strip()}")
    if include_output_schema:
        sections.append(
            "HỢP ĐỒNG OUTPUT BẮT BUỘC\n"
            "Chỉ trả JSON thuần, không bỏ hoặc đổi tên field:\n"
            + build_output_schema(source_type, assignment)
        )
    sections.append("chỉ được trả về text json")
    return "\n\n".join(section for section in sections if section)
