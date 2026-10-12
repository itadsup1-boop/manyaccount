"""Evidence-pack helpers for videos sourced from TikTok/Facebook.

Social captions are often incomplete.  This module keeps caption, transcript,
OCR and provenance as separate fields while exposing one deterministic text
view to the existing EvidenceGuard and VisualGrounding checks.  Transcript and
OCR producers can be added later without changing the pipeline contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _unique_parts(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


@dataclass(frozen=True)
class SocialEvidencePack:
    source_type: str
    source_url: str
    caption: str
    transcript: str
    ocr_text: str
    creator: str
    published_at: str
    source_text: str
    has_caption: bool
    has_transcript: bool
    has_ocr: bool
    coverage_score: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_social_evidence_pack(
    *,
    source_type: str,
    source_url: str = "",
    caption: str = "",
    transcript: str = "",
    ocr_text: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> SocialEvidencePack:
    """Build a normalized evidence view without trusting any single field.

    ``transcript`` and ``ocr_text`` are optional so existing crawlers remain
    backward compatible.  When absent, the resulting coverage score is lower
    and the social gate records a review warning instead of pretending that a
    caption fully represents the video.
    """
    metadata = metadata or {}
    caption_text = _text(caption) or _text(metadata.get("description")) or _text(metadata.get("title"))
    transcript_text = _text(transcript) or _text(metadata.get("transcript"))
    ocr_value = _text(ocr_text) or _text(metadata.get("ocr_text"))
    parts = _unique_parts(caption_text, transcript_text, ocr_value)
    creator = _text(
        metadata.get("creator")
        or metadata.get("author")
        or metadata.get("source_name")
    )
    published_at = _text(
        metadata.get("published_at")
        or metadata.get("timestamp")
        or metadata.get("upload_date")
    )
    coverage_score = 0
    if caption_text:
        coverage_score += 40
    if transcript_text:
        coverage_score += 40
    if ocr_value:
        coverage_score += 20
    return SocialEvidencePack(
        source_type=_text(source_type).lower(),
        source_url=_text(source_url),
        caption=caption_text,
        transcript=transcript_text,
        ocr_text=ocr_value,
        creator=creator,
        published_at=published_at,
        source_text=" ".join(parts),
        has_caption=bool(caption_text),
        has_transcript=bool(transcript_text),
        has_ocr=bool(ocr_value),
        coverage_score=min(100, coverage_score),
    )

