"""Validation cho nguồn Facebook Page cũ của API layer."""

from __future__ import annotations

from typing import Any, Mapping

from apps.creator_facebook.facebook_pipeline.source_config import (
    normalize_page_source_record,
    sanitize_page_source_payload,
)


def normalize_api_source(source: Mapping[str, Any]) -> dict[str, Any]:
    result = normalize_page_source_record(source)
    if not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = "Adsupnews"
    return result


def prepare_api_source_payload(
    payload: Mapping[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    result = sanitize_page_source_payload(payload, partial=partial)
    if not partial and not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = "Adsupnews"
    if "id_tiktok" in result and not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = "Adsupnews"
    return result
