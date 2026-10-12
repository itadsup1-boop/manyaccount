"""Utilities for recognizing a complete JSON response from Gemini Web."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any


SCRIPT_ROOT_KEYS = frozenset(
    {
        "title_tiktok",
        "script_voice",
        "hook",
        "beats",
        "edit_plan",
        "content_type",
    }
)

REFUSAL_MARKERS = (
    "tôi là một mô hình ngôn ngữ",
    "nằm ngoài mục đích mà tôi được tạo ra",
    "tôi không thể hỗ trợ yêu cầu này",
    "tôi không thể giúp bạn với yêu cầu này",
    "i am a language model",
    "i'm a language model",
    "outside the purpose i was designed for",
    "i can't assist with that request",
    "i cannot assist with that request",
)


def _json_candidates(text: str) -> list[str]:
    """Return likely JSON snippets while preserving their order in the response."""
    cleaned = (text or "").lstrip("\ufeff").strip()
    if not cleaned:
        return []

    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE):
        block = match.group(1).strip()
        if block:
            candidates.append(block)

    # raw_decode below can ignore prose before/after a JSON object. Keeping the
    # full text also handles Gemini's code block UI where the backticks are not
    # exposed through textContent.
    candidates.append(cleaned)
    return candidates


def _decode_objects(candidate: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []

    for match in re.finditer(r"\{", candidate):
        try:
            value, _end = decoder.raw_decode(candidate, match.start())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            objects.append(value)

    if objects:
        return objects

    # Gemini occasionally leaves a trailing comma immediately before ] or }.
    relaxed = re.sub(r",\s*([\]}])", r"\1", candidate)
    if relaxed != candidate:
        for match in re.finditer(r"\{", relaxed):
            try:
                value, _end = decoder.raw_decode(relaxed, match.start())
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(value, dict):
                objects.append(value)

    return objects


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract the most likely complete JSON object from Gemini response text."""
    objects: list[dict[str, Any]] = []
    for candidate in _json_candidates(text):
        objects.extend(_decode_objects(candidate))

    if not objects:
        return None

    # Prefer a root object matching the script contract. If several nested
    # objects were decoded, the root normally has both more keys and more data.
    return max(
        objects,
        key=lambda item: (
            bool(SCRIPT_ROOT_KEYS.intersection(item)),
            len(SCRIPT_ROOT_KEYS.intersection(item)),
            len(item),
            len(json.dumps(item, ensure_ascii=False)),
        ),
    )


def is_script_payload(payload: object) -> bool:
    return isinstance(payload, dict) and bool(SCRIPT_ROOT_KEYS.intersection(payload))


def is_refusal_response(text: str) -> bool:
    """Recognize Gemini's short capability/refusal answer, not normal script text."""
    normalized = " ".join(str(text or "").lower().split())
    if not normalized or len(normalized) > 1_500:
        return False
    if any(marker in normalized for marker in REFUSAL_MARKERS):
        return True

    # Gemini changes the exact wording frequently. Capability refusals still
    # combine a model-identity phrase with an inability phrase.
    mentions_language_model = (
        "mô hình ngôn ngữ" in normalized
        or "language model" in normalized
    )
    claims_inability = any(
        marker in normalized
        for marker in (
            "không thể",
            "không có khả năng",
            "cannot",
            "can't",
            "unable to",
        )
    )
    return mentions_language_model and claims_inability


def select_latest_script_response(
    response_texts: Iterable[str],
) -> tuple[dict[str, Any] | None, str]:
    """Select a valid script from the newest parseable Gemini response text."""
    texts = [str(text or "").strip() for text in response_texts]
    for text in reversed(texts):
        if not text:
            continue
        payload = extract_json_from_text(text)
        if is_script_payload(payload):
            return payload, text
    return None, texts[-1] if texts else ""
