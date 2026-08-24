"""Deterministic, low-cost ranking for source candidates.

The ranker deliberately runs before downloading media or calling an LLM.  It
only uses metadata that a crawler already has, and treats candidates with too
little metadata as ``unscored`` instead of rejecting them.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_THRESHOLDS = {
    "reject": 55,
    "ready": 65,
    "priority": 80,
}

_STOP_WORDS = {
    "anh", "bi", "cai", "cac", "cho", "co", "cua", "da", "dang", "day",
    "de", "den", "duoc", "gi", "hay", "khi", "la", "lai", "mot", "nay",
    "nhung", "o", "qua", "sau", "se", "tai", "the", "thi", "tren", "tu",
    "va", "ve", "voi",
}
_HOOK_WORDS = {
    "bat ngo", "canh bao", "chan dong", "gay soc", "he lo", "khong ngo",
    "ky la", "moi nhat", "nong", "su that", "tranh cai", "vi sao",
}
_PAYOFF_WORDS = {
    "anh huong", "can biet", "co loi", "gia", "hau qua", "lam gi", "loi ich",
    "mat tien", "nguy co", "rui ro", "tiet kiem", "tranh", "xu ly",
}


def _plain(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token for token in _plain(value).split()
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _candidate_dict(candidate: Any, index: int) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        result = dict(candidate)
    else:
        result = {"url": str(candidate or "")}
    result.setdefault("position", index)
    return result


def _candidate_text(candidate: Mapping[str, Any]) -> str:
    parts = [
        candidate.get("title"),
        candidate.get("caption"),
        candidate.get("description"),
        candidate.get("summary"),
    ]
    return " ".join(str(part).strip() for part in parts if part).strip()


def _profile_keywords(profile: Mapping[str, Any] | None) -> set[str]:
    if not profile:
        return set()
    values: list[str] = []
    for key in (
        "channel_name", "topic", "niche", "audience", "content_pillars",
        "audience_pains", "keywords", "preferred_topics",
    ):
        value = profile.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return _tokens(" ".join(values))


def _has_any(plain_text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in plain_text for phrase in phrases)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        try:
            result = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _number(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    raw = str(value or "").strip().lower().replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb]?)", raw)
    if not match:
        return 0
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    return max(0, int(float(match.group(1)) * multiplier[match.group(2)]))


@dataclass(frozen=True)
class CandidateScore:
    total_score: int
    status: str
    metadata_confidence: str
    breakdown: dict[str, int]
    reasons: tuple[str, ...]
    original_index: int

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


def score_candidate(
    candidate: Any,
    profile: Mapping[str, Any] | None = None,
    source_type: str = "",
    *,
    index: int = 0,
    now: datetime | None = None,
    thresholds: Mapping[str, int] | None = None,
) -> CandidateScore:
    """Score one candidate on the six dimensions in the video roadmap."""
    item = _candidate_dict(candidate, index)
    text = _candidate_text(item)
    plain_text = _plain(text)
    text_tokens = _tokens(text)
    profile_tokens = _profile_keywords(profile)
    url = str(item.get("url") or item.get("webpage_url") or "").strip()
    reasons: list[str] = []

    overlap = len(text_tokens & profile_tokens)
    if not text:
        topic_fit = 10
    elif not profile_tokens:
        topic_fit = 15
    elif overlap >= 4:
        topic_fit = 25
        reasons.append("khớp chủ đề kênh rất tốt")
    elif overlap >= 2:
        topic_fit = 20
        reasons.append("khớp chủ đề kênh")
    elif overlap == 1:
        topic_fit = 14
    else:
        topic_fit = 5

    hook = 4 if not text else 8
    if re.search(r"\d", text):
        hook += 4
        reasons.append("có chi tiết định lượng")
    if _has_any(plain_text, _HOOK_WORDS):
        hook += 5
        reasons.append("có tín hiệu hook")
    if 25 <= len(text) <= 220:
        hook += 3
    if "?" in text or ":" in text:
        hook += 2
    hook = min(20, hook)

    evidence = 0
    if url.startswith(("http://", "https://")):
        evidence += 5
    if len(text) >= 35:
        evidence += 5
    if re.search(r"\d", text):
        evidence += 4
    if item.get("author") or item.get("source_name"):
        evidence += 3
    if item.get("evidence_count") or item.get("source_text"):
        evidence += 3
    evidence = min(20, evidence)

    normalized_type = _plain(source_type)
    visual = 10 if normalized_type in {"facebook", "tiktok", "video"} else 3
    if item.get("thumbnail") or item.get("has_image") or item.get("image_count"):
        visual += 3
    if item.get("duration") or item.get("has_video"):
        visual += 2
    visual = min(15, visual)

    payoff = 3 if text else 1
    if _has_any(plain_text, _PAYOFF_WORDS):
        payoff += 4
        reasons.append("nêu tác động hoặc lợi ích")
    audience_tokens = _tokens((profile or {}).get("audience_pains", ""))
    if audience_tokens and text_tokens & audience_tokens:
        payoff += 3
    payoff = min(10, payoff)

    current = now or datetime.now(timezone.utc)
    published = _parse_datetime(
        item.get("published_at") or item.get("timestamp") or item.get("upload_date")
    )
    if published:
        age_hours = max(0.0, (current - published).total_seconds() / 3600)
        if age_hours <= 24:
            recency = 10
        elif age_hours <= 72:
            recency = 8
        elif age_hours <= 168:
            recency = 6
        else:
            recency = 3
    else:
        position = _number(item.get("position"))
        recency = 10 if position == 0 else 8 if position <= 2 else 6 if position <= 5 else 4
    engagement = sum(
        _number(item.get(key))
        for key in ("view_count", "like_count", "comment_count")
    )
    if engagement:
        recency = min(10, recency + min(2, int(math.log10(engagement + 1) / 3)))

    breakdown = {
        "channel_topic_fit": topic_fit,
        "clear_hook": hook,
        "facts_evidence": evidence,
        "storytelling_visuals": visual,
        "payoff": payoff,
        "recency_interest": recency,
    }
    total = sum(breakdown.values())
    metadata_signals = sum(
        bool(value) for value in (
            text, url, item.get("thumbnail"), item.get("timestamp"),
            item.get("view_count"), item.get("duration"),
        )
    )
    if not text or len(text) < 12:
        confidence = "low"
        status = "unscored"
        reasons.append("thiếu metadata, giữ lại để tránh bỏ sót")
    else:
        confidence = "high" if metadata_signals >= 3 or len(text) >= 35 else "medium"
        limits = dict(DEFAULT_THRESHOLDS)
        limits.update(thresholds or {})
        if total < limits["reject"]:
            status = "reject"
        elif total < limits["ready"]:
            status = "queue"
        elif total < limits["priority"]:
            status = "ready"
        else:
            status = "priority"

    return CandidateScore(
        total_score=total,
        status=status,
        metadata_confidence=confidence,
        breakdown=breakdown,
        reasons=tuple(reasons),
        original_index=index,
    )


def rank_candidates(
    candidates: Iterable[Any],
    profile: Mapping[str, Any] | None = None,
    source_type: str = "",
    *,
    thresholds: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Return enriched candidates ordered by priority, score, then source order."""
    ranked: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        item = _candidate_dict(candidate, index)
        score = score_candidate(
            item,
            profile,
            source_type,
            index=index,
            thresholds=thresholds,
        )
        item["source_rank"] = score.to_dict()
        ranked.append(item)

    status_order = {"priority": 0, "ready": 1, "queue": 2, "unscored": 3, "reject": 4}
    ranked.sort(
        key=lambda item: (
            status_order.get(item["source_rank"]["status"], 5),
            -item["source_rank"]["total_score"],
            item["source_rank"]["original_index"],
        )
    )
    return ranked


def should_process_candidate(candidate: Mapping[str, Any]) -> bool:
    """Fail open for low-metadata candidates, reject only confident poor matches."""
    rank = candidate.get("source_rank") or {}
    return not (
        rank.get("status") == "reject"
        and rank.get("metadata_confidence") in {"medium", "high"}
    )
