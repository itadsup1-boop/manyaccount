"""Validation cho nguồn Facebook Group lưu ở bảng riêng."""

from __future__ import annotations

from typing import Any, Mapping

from apps.creator_facebook.facebook_pipeline.source_config import (
    normalize_group_source_record,
    sanitize_group_source_payload,
)


DEFAULT_TARGET_CHANNEL = "Adsupnews"


def normalize_group_api_source(source: Mapping[str, Any]) -> dict[str, Any]:
    result = normalize_group_source_record(source)
    if not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = DEFAULT_TARGET_CHANNEL
    return result


def prepare_group_api_source_payload(
    payload: Mapping[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    result = sanitize_group_source_payload(payload, partial=partial)
    if not partial and not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = DEFAULT_TARGET_CHANNEL
    if "id_tiktok" in result and not str(result.get("id_tiktok") or "").strip():
        result["id_tiktok"] = DEFAULT_TARGET_CHANNEL
    return result
