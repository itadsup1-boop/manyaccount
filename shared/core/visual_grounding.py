"""Deterministic checks that visual beats stay grounded in source evidence."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


import os
from shared.core.evidence_guard import EVIDENCE_GUARD_ENABLED

VISUAL_GROUNDING_ENABLED = os.environ.get(
    "VISUAL_GROUNDING_ENABLED",
    "1" if EVIDENCE_GUARD_ENABLED else "0",
).lower() in ("1", "true")

_STOPWORDS = {
    "anh", "hinh", "canh", "video", "hien", "thay", "cho", "voi", "dang",
    "mot", "nhung", "nguoi", "vat", "su", "kien", "the", "la", "va", "trong",
    "the", "a", "an", "the", "of", "in", "on", "at", "to", "and", "with",
}


def _plain(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token for token in _plain(value).split()
        if len(token) > 2 and token not in _STOPWORDS
    }


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


@dataclass(frozen=True)
class VisualGroundingReport:
    passed: bool
    score: int
    required_beats: int
    grounded_beats: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def guard_visual_grounding(
    content: Mapping[str, Any],
    *,
    source_text: str = "",
    source_type: str = "",
    assets: Sequence[Mapping[str, Any]] | None = None,
) -> VisualGroundingReport:
    """Require each beat's visual anchors to occur in source/evidence text.

    This is intentionally text-based and deterministic. It does not claim that
    a pixel-level vision model verified an image; it prevents unsupported
    subjects/actions from reaching the renderer and records missing metadata.
    """
    if not VISUAL_GROUNDING_ENABLED:
        return VisualGroundingReport(
            passed=True,
            score=100,
            required_beats=0,
            grounded_beats=0,
            errors=(),
            warnings=(),
        )

    errors: list[str] = []
    warnings: list[str] = []
    beats = [
        beat for beat in (content.get("beats") or content.get("visual_beats") or [])
        if isinstance(beat, Mapping)
    ]
    evidence_text = " ".join(
        str(item.get("source_text") or item.get("detail") or "")
        for item in (content.get("evidence") or [])
        if isinstance(item, Mapping)
    )
    claim_text = " ".join(
        str(item.get("claim") or "")
        for item in (content.get("claim_register") or [])
        if isinstance(item, Mapping)
    )
    source_tokens = _tokens(" ".join((source_text, evidence_text, claim_text)))
    grounded_beats = 0

    if not beats:
        errors.append("VISUAL_BEATS_MISSING: Không có beat hình ảnh để kiểm tra.")

    for index, beat in enumerate(beats, start=1):
        query = str(beat.get("visual_query") or "").strip()
        must_show = [
            str(value).strip()
            for value in _list(beat.get("must_show"))
            if str(value).strip()
        ]
        if not query:
            errors.append(f"BEAT_{index}_VISUAL_QUERY_MISSING: Beat thiếu visual_query.")
            continue

        beat_grounded = False
        query_tokens = _tokens(query)
        if query_tokens and source_tokens & query_tokens:
            beat_grounded = True

        for visual in must_show:
            visual_tokens = _tokens(visual)
            if not visual_tokens:
                continue
            if not source_tokens & visual_tokens:
                errors.append(
                    f"BEAT_{index}_MUST_SHOW_UNGROUNDED: '{visual}' không có trong nguồn/evidence."
                )
            else:
                beat_grounded = True

        if not beat_grounded:
            errors.append(
                f"BEAT_{index}_VISUAL_UNGROUNDED: visual_query không neo vào nguồn/evidence."
            )
        else:
            grounded_beats += 1

    for index, asset in enumerate(assets or [], start=1):
        if not isinstance(asset, Mapping):
            errors.append(f"ASSET_{index}_INVALID: Asset hình ảnh không hợp lệ.")
            continue
        if not str(asset.get("path") or asset.get("local_path") or "").strip():
            errors.append(f"ASSET_{index}_PATH_MISSING: Asset thiếu đường dẫn local.")
        grounding_text = str(
            asset.get("grounding_text")
            or asset.get("alt")
            or asset.get("caption")
            or asset.get("search_query")
            or ""
        ).strip()
        if not grounding_text:
            warnings.append(
                f"ASSET_{index}_GROUNDING_METADATA_MISSING: Chưa có alt/caption/search_query."
            )
        elif source_tokens and not (_tokens(grounding_text) & source_tokens):
            warnings.append(
                f"ASSET_{index}_GROUNDING_UNVERIFIED: Metadata asset chưa khớp nguồn."
            )

    score = max(0, 100 - 25 * len(errors) - 6 * len(warnings))
    return VisualGroundingReport(
        passed=not errors and score >= 65,
        score=score,
        required_beats=len(beats),
        grounded_beats=grounded_beats,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def summarize_visual_grounding(report: VisualGroundingReport) -> str:
    if report.passed:
        return (
            f"Visual grounding đạt {report.score}/100; "
            f"beats {report.grounded_beats}/{report.required_beats}."
        )
    return "; ".join(report.errors + report.warnings)
