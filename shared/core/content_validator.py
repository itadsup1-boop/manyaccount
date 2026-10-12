"""Kiểm định nội dung bằng luật xác định trước khi tạo TTS."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Mapping

from shared.core.content_models import CLAIM_TYPES, STORY_TYPES
from shared.core.evidence_guard import EVIDENCE_GUARD_ENABLED


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


def _sentences(value: Any) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?:[.!?…]+\s+|\n+)", str(value or ""))
        if sentence.strip()
    ]


def _numeric_values(value: Any) -> list[str]:
    matches = re.findall(r"(?<![\w])\d[\d.,]*", str(value or ""))
    return list(dict.fromkeys(match.strip() for match in matches if match.strip()))


def _numeric_key(value: Any) -> str:
    text = str(value or "").strip().replace(",", ".")
    text = re.sub(r"[^0-9.]", "", text)
    # Câu tiếng Việt thường kết thúc bằng số rồi dấu câu ("từ năm 2027.",
    # "ngày 25, 26"), khiến số bị nuốt luôn dấu chấm/phẩy và không khớp với
    # cùng con số đã đăng ký. Bỏ dấu thừa ở hai đầu.
    return text.strip(".")


def _claim_surface_texts(content: Mapping[str, Any]) -> list[str]:
    surfaces: list[str] = []
    # ``main_angle`` và ``audience_payoff`` là metadata biên tập (mô tả góc
    # tiếp cận và lợi ích người xem), không phải câu được đọc lên hay hiển thị
    # trên video. Bắt chúng đăng ký claim + evidence tạo yêu cầu không thể đáp
    # ứng và chặn oan mọi kịch bản.
    for field_name in (
        "title_tiktok",
        "main_idea",
        "selected_hook",
        "script_voice",
    ):
        surfaces.extend(_sentences(content.get(field_name)))

    fact_sheet = content.get("fact_sheet")
    if isinstance(fact_sheet, Mapping):
        # ``who``/``when``/``where`` là bảng tra cứu thực thể, mốc thời gian và
        # địa điểm ("ông Nguyễn Văn Hưởng", "gặp lại cuối năm 2023") — mảnh dữ
        # kiện giúp AI viết đúng, không phải câu khẳng định được đọc lên video.
        # Bắt từng mảnh đăng ký claim + evidence tạo hàng loạt false-positive.
        # Chỉ các trường diễn đạt thành khẳng định mới cần đăng ký.
        for field_name in ("what", "cause", "impact", "confirmed_facts"):
            value = fact_sheet.get(field_name)
            values = value if isinstance(value, list) else [value]
            surfaces.extend(_compact(item) for item in values if _compact(item))

    for beat in content.get("beats", []):
        if not isinstance(beat, Mapping):
            continue
        # ``must_show`` là chỉ dẫn dựng hình, không phải câu factual được
        # đọc/hiển thị; bắt buộc đăng ký nó như claim tạo nhiều false-positive.
        for field_name in ("voice_over", "on_screen_text"):
            value = beat.get(field_name)
            values = value if isinstance(value, list) else [value]
            surfaces.extend(_compact(item) for item in values if _compact(item))
    return surfaces


_INSTRUCTION_PREFIXES = (
    "cách ",
    "hãy ",
    "nên ",
    "đừng ",
    "lưu ý ",
    "khi thời tiết ",
    "để an toàn ",
)

# Cụm chỉ dấu lời khuyên/nhận định biên tập có thể nằm giữa câu, ví dụ
# "Vì vậy, trước khi xuống tiền, hãy ngồi thử hàng ghế sau." Những câu này
# không phải khẳng định sự kiện nên bài nguồn không thể có evidence cho chúng;
# bắt đăng ký claim sẽ chặn oan kịch bản.
_INSTRUCTION_MARKERS = (
    " hãy ",
    " đừng ",
    " bạn nên ",
    " nên kiểm tra",
    " nên thử",
    " nên ngồi thử",
    " cần kiểm tra",
    " cần lưu ý",
    "đáng cân nhắc",
    "đáng kiểm tra",
    "nên cân nhắc",
    "điểm cần nhớ",
    "trước khi xuống tiền",
    "trước khi quyết định",
    # Editorial/scene-transition phrasing is descriptive glue, not a standalone
    # factual claim that needs a separate source citation.
    "điểm đáng chú ý",
    "chi tiết nằm ở đây",
    "các cảnh trong video",
    "dòng chữ được hiển thị",
)

VISUAL_RECAP_MARKERS = (
    "video cho thấy",
    "phần mô tả",
    "hình ảnh cho thấy",
    "video mở bằng",
    "máy quay",
    "góc quay",
    "cảnh tiếp theo",
    "sau đó là",
    "dòng chữ cho biết",
)


def _is_instruction_surface(value: Any) -> bool:
    """Nhận diện câu hướng dẫn/nhận định cho người xem, không phải khẳng định
    sự kiện cần bằng chứng."""
    text = _compact(value).casefold()
    # Câu hỏi là CTA mời bình luận ("Bạn thấy ... không?"), không khẳng định
    # điều gì nên bài nguồn không thể có bằng chứng cho nó.
    if text.endswith("?"):
        return True
    if text.startswith(_INSTRUCTION_PREFIXES):
        return True
    padded = f" {text} "
    return any(marker in padded for marker in _INSTRUCTION_MARKERS)


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
    elif len(hook_words) < 10 or len(hook_words) > 16:
        add_warning(
            "HOOK_LENGTH_OUTSIDE_TARGET",
            "Hook nên nằm trong khoảng mục tiêu 10–16 từ.",
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
    if len(script_words) < 120:
        add_error(
            "SCRIPT_TOO_SHORT",
            "script_voice quá ngắn cho bản tin 50-55 giây; cần ít nhất 120 từ.",
            "script_voice",
            "structure",
            10,
        )
    elif len(script_words) > 165:
        add_error(
            "SCRIPT_TOO_LONG",
            "script_voice vượt quá 165 từ cho bản tin ngắn.",
            "script_voice",
            "structure",
            10,
        )
    elif len(script_words) < 135 or len(script_words) > 155:
        add_warning(
            "SCRIPT_OUTSIDE_TARGET",
            "script_voice nằm ngoài khoảng mục tiêu 135–155 từ.",
            "script_voice",
            "structure",
        )

    script_key = _key(script)
    visual_recap_hits = [
        marker for marker in VISUAL_RECAP_MARKERS
        if marker in script_key
    ]
    if len(visual_recap_hits) >= 3:
        add_error(
            "SCRIPT_VISUAL_RECAP",
            "Lời thoại đang kể lại khung hình thay vì dẫn bản tin; hãy dùng hình ảnh làm bằng chứng và tập trung vào sự kiện, diễn biến, tác động.",
            "script_voice",
            "clarity",
            10,
        )
    elif visual_recap_hits:
        add_warning(
            "SCRIPT_VISUAL_NARRATION",
            "Hạn chế cách kể theo khung hình; lời thoại cần ưu tiên sự kiện và ý nghĩa.",
            "script_voice",
            "clarity",
            3,
        )

    script_sentences = _sentences(script)

    repeated_sentence_pairs = []
    for first_index, first in enumerate(script_sentences):
        if len(_words(first)) < 5:
            continue
        for second_index in range(first_index + 1, len(script_sentences)):
            second = script_sentences[second_index]
            if len(_words(second)) < 5:
                continue
            if SequenceMatcher(None, _key(first), _key(second)).ratio() >= 0.88:
                repeated_sentence_pairs.append((first_index + 1, second_index + 1))
    if repeated_sentence_pairs:
        add_error(
            "SCRIPT_SENTENCES_REPEATED",
            "Các câu trong script đang lặp lại cùng một ý; mỗi câu phải thêm thông tin mới.",
            "script_voice",
            "clarity",
            6,
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

    if source_type == "article":
        fact_sheet = content.get("fact_sheet")
        if not isinstance(fact_sheet, Mapping):
            add_error(
                "FACT_SHEET_MISSING",
                "Bài article phải có fact_sheet trước khi viết kịch bản.",
                "fact_sheet",
                "structure",
                12,
            )
        else:
            who = fact_sheet.get("who")
            confirmed_facts = fact_sheet.get("confirmed_facts")
            who_items = who if isinstance(who, list) else [who] if who else []
            confirmed_items = (
                confirmed_facts
                if isinstance(confirmed_facts, list)
                else [confirmed_facts] if confirmed_facts else []
            )
            who_items = [item for item in who_items if _compact(item)]
            confirmed_items = [
                item for item in confirmed_items if _compact(item)
            ]
            if not who_items:
                add_error(
                    "FACT_SHEET_WHO_MISSING",
                    "fact_sheet.who phải có nhân vật, tổ chức hoặc nhóm người cụ thể.",
                    "fact_sheet.who",
                    "structure",
                    6,
                )
            if not _compact(fact_sheet.get("what")):
                add_error(
                    "FACT_SHEET_WHAT_MISSING",
                    "fact_sheet.what phải nêu sự kiện chính bằng một câu cụ thể.",
                    "fact_sheet.what",
                    "structure",
                    8,
                )
            if len(confirmed_items) < 2:
                add_error(
                    "FACT_SHEET_FACTS_THIN",
                    "fact_sheet.confirmed_facts cần ít nhất hai dữ kiện đã xác nhận.",
                    "fact_sheet.confirmed_facts",
                    "evidence",
                    10,
                )
            if not _compact(fact_sheet.get("impact")):
                add_warning(
                    "FACT_SHEET_IMPACT_MISSING",
                    "fact_sheet.impact đang trống; payoff có thể thiếu tác động rõ.",
                    "fact_sheet.impact",
                    "structure",
                )
            anchor_text = " ".join(
                [
                    " ".join(str(item) for item in who_items),
                    str(fact_sheet.get("what") or ""),
                ]
            )
            anchor_tokens = set(_words(anchor_text)) - {
                "vụ", "việc", "người", "nhóm", "đã", "đang", "một",
                "này", "khiến", "tại", "cho", "với",
            }
            hook_tokens = set(_words(selected_hook))
            if anchor_tokens and not anchor_tokens.intersection(hook_tokens):
                add_error(
                    "HOOK_NOT_GROUNDED_IN_FACT_SHEET",
                    "selected_hook phải nêu ít nhất một chủ thể hoặc sự kiện trong fact_sheet.",
                    "selected_hook",
                    "hook",
                    8,
                )
    claim_register = [
        item for item in content.get("claim_register", [])
        if isinstance(item, Mapping)
    ] if EVIDENCE_GUARD_ENABLED else []
    if EVIDENCE_GUARD_ENABLED and not claim_register:
        add_error(
            "CLAIM_REGISTER_MISSING",
            "Báº¯t buá»™c khai bÃ¡o claim_register cho má»i claim vÃ  sá»‘ liá»‡u.",
            "claim_register",
            "evidence",
            14,
        )

    claim_ids: set[str] = set()
    registered_numbers: set[str] = set()
    for index, item in enumerate(claim_register):
        claim_id = _compact(item.get("claim_id"))
        claim = _compact(item.get("claim"))
        claim_type = _compact(item.get("claim_type") or "fact").lower()
        if not claim_id:
            add_error(
                "CLAIM_ID_MISSING",
                f"Claim #{index + 1} thiáº¿u claim_id duy nháº¥t.",
                "claim_register",
                "evidence",
                5,
            )
        elif claim_id in claim_ids:
            add_error(
                "CLAIM_ID_DUPLICATE",
                f"claim_id {claim_id} bá»‹ trÃ¹ng.",
                "claim_register",
                "evidence",
                5,
            )
        else:
            claim_ids.add(claim_id)
        if not claim:
            add_error(
                "CLAIM_TEXT_MISSING",
                f"Claim #{index + 1} thiáº¿u ná»™i dung claim.",
                "claim_register",
                "evidence",
                6,
            )
        if claim_type not in CLAIM_TYPES:
            add_error(
                "CLAIM_TYPE_INVALID",
                f"Claim {claim_id or index + 1} cÃ³ claim_type khÃ´ng há»£p lá»‡.",
                "claim_register.claim_type",
                "evidence",
                3,
            )
        values = item.get("numeric_values") or []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        claim_numbers = {
            _numeric_key(value)
            for value in (values or _numeric_values(claim))
            if _numeric_key(value)
        }
        claim_numbers.update(
            _numeric_key(value) for value in _numeric_values(claim) if _numeric_key(value)
        )
        registered_numbers.update(claim_numbers)

    evidence = [
        item for item in content.get("evidence", [])
        if isinstance(item, Mapping)
    ] if EVIDENCE_GUARD_ENABLED else []
    evidence_claim_ids = {
        _compact(item.get("claim_id")) for item in evidence if _compact(item.get("claim_id"))
    }
    for item in evidence:
        if not _compact(item.get("claim_id")):
            add_error(
                "EVIDENCE_CLAIM_ID_MISSING",
                "Mỗi evidence phải trỏ tới claim_id cụ thể.",
                "evidence.claim_id",
                "evidence",
                6,
            )
        elif _compact(item.get("claim_id")) not in claim_ids:
            add_error(
                "EVIDENCE_ORPHAN_CLAIM",
                f"Evidence trỏ tới claim_id chưa đăng ký: {_compact(item.get('claim_id'))}.",
                "evidence.claim_id",
                "evidence",
                6,
            )
    for claim_id in claim_ids:
        if claim_id not in evidence_claim_ids:
            add_error(
                "CLAIM_WITHOUT_EVIDENCE",
                f"Claim {claim_id} chưa có evidence tương ứng.",
                "claim_register",
                "evidence",
                8,
            )

    registered_claim_texts = [
        _compact(item.get("claim"))
        for item in claim_register
        if _compact(item.get("claim"))
    ]
    unregistered_surfaces = []
    seen_unregistered_keys = set()
    for surface in (
        _claim_surface_texts(content) if EVIDENCE_GUARD_ENABLED else []
    ):
        if _is_instruction_surface(surface):
            continue
        surface_words = set(_words(surface))
        if len(surface_words) < 4:
            continue
        if not any(
            _key(surface) in _key(claim)
            or _key(claim) in _key(surface)
            or (
                surface_words
                and len(surface_words & set(_words(claim))) / len(surface_words) >= 0.55
            )
            for claim in registered_claim_texts
        ):
            # A single sentence can intentionally combine multiple independently
            # registered observations (for example, "a woman is interviewed and
            # a group is standing together").  In that case no individual claim
            # covers the whole sentence, but the claim_register entries together
            # do.  Count the union of words covered by all claims before rejecting
            # the surface; evidence is still required for every registered claim
            # by the checks above.
            covered_words = set()
            contributing_claims = 0
            for claim in registered_claim_texts:
                claim_words = set(_words(claim))
                overlap = surface_words & claim_words
                if overlap:
                    contributing_claims += 1
                    covered_words.update(overlap)
            if (
                contributing_claims >= 2
                and len(covered_words) / len(surface_words) >= 0.55
            ):
                continue
            # The same sentence often appears in more than one surface field
            # (e.g. script_voice and the beat voice_over it was split from) —
            # count it once, not once per occurrence.
            surface_key = _key(surface)
            if surface_key in seen_unregistered_keys:
                continue
            seen_unregistered_keys.add(surface_key)
            unregistered_surfaces.append(surface)
    if unregistered_surfaces:
        surface_preview = "; ".join(
            _compact(item)[:120] for item in unregistered_surfaces[:8]
        )
        add_error(
            "CLAIM_SURFACE_UNREGISTERED",
            "Mỗi claim trong nội dung phải có dòng claim_register tương ứng; "
            f"còn thiếu {len(unregistered_surfaces)} claim. "
            f"Các claim cần đăng ký: {surface_preview}",
            "claim_register",
            "evidence",
            10,
        )

    missing_numeric_claims = []
    for surface in (
        _claim_surface_texts(content) if EVIDENCE_GUARD_ENABLED else []
    ):
        for numeric_value in _numeric_values(surface):
            if _numeric_key(numeric_value) not in registered_numbers:
                missing_numeric_claims.append(numeric_value)
    if missing_numeric_claims:
        add_error(
            "NUMERIC_CLAIM_UNREGISTERED",
            "Mọi số liệu trong nội dung phải xuất hiện trong claim_register: "
            + ", ".join(sorted(set(missing_numeric_claims)))
            + ". Hãy thêm từng số vào numeric_values và evidence.source_text.",
            "claim_register.numeric_values",
            "evidence",
            10,
        )

    valid_evidence = [
        item
        for item in evidence
        if _compact(item.get("claim_id"))
        and _compact(item.get("claim"))
        and _compact(item.get("source_text"))
    ]
    if EVIDENCE_GUARD_ENABLED and not valid_evidence:
        add_error(
            "EVIDENCE_MISSING",
            "Cần ít nhất một evidence có claim và source_text/observed_detail.",
            "evidence",
            "evidence",
            14,
        )
    elif (
        EVIDENCE_GUARD_ENABLED
        and source_type == "article"
        and len(valid_evidence) < 2
    ):
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
    if (
        EVIDENCE_GUARD_ENABLED
        and high_risk_evidence
        and len(reliable_evidence) < 2
    ):
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
