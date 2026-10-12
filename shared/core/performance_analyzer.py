"""Normalize TikTok metrics and build outlier-resistant performance summaries."""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


MEASUREMENT_WINDOWS = (2, 24, 72, 168)
WINDOW_TOLERANCE_HOURS = {2: 1.0, 24: 3.0, 72: 8.0, 168: 18.0}


def _key(value: Any) -> str:
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def parse_number(value: Any, *, rate: bool = False) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().lower().replace(" ", "")
        is_percent = "%" in text
        suffix_multiplier = 1.0
        suffixes = {
            "k": 1_000.0,
            "m": 1_000_000.0,
            "b": 1_000_000_000.0,
            "nghin": 1_000.0,
            "trieu": 1_000_000.0,
        }
        normalized_suffix = _key(text).replace("_", "")
        for suffix, multiplier in suffixes.items():
            if normalized_suffix.endswith(suffix):
                suffix_multiplier = multiplier
                text = text[: -len(suffix)]
                break
        text = text.replace("%", "")
        text = re.sub(r"[^0-9,.-]", "", text)
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            decimal_part = text.rsplit(",", 1)[-1]
            if (rate or is_percent or suffix_multiplier != 1.0) and len(decimal_part) <= 2:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        try:
            number = float(text or 0) * suffix_multiplier
        except ValueError:
            number = 0.0
        if is_percent:
            number /= 100.0
    if not math.isfinite(number):
        return 0.0
    if rate and number > 1.0:
        number /= 100.0
    return max(0.0, number)


def _datetime(value: Any, *, default: datetime | None = None) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if not text:
            parsed = default
        else:
            parsed = None
            iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = datetime.fromisoformat(iso_text)
            except ValueError:
                for pattern in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                    "%d/%m/%Y %H:%M:%S",
                    "%Y-%m-%d",
                    "%d/%m/%Y",
                ):
                    try:
                        parsed = datetime.strptime(text, pattern)
                        break
                    except ValueError:
                        continue
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def normalize_measurement_window(
    value: Any,
    *,
    published_at: str = "",
    measured_at: str = "",
) -> str:
    text = _key(value)
    explicit = {
        "2": "2h", "2h": "2h", "2_gio": "2h", "2_hours": "2h",
        "24": "24h", "24h": "24h", "24_gio": "24h", "1d": "24h",
        "72": "72h", "72h": "72h", "72_gio": "72h", "3d": "72h",
        "168": "168h", "168h": "168h", "7d": "168h", "7_ngay": "168h",
    }
    if text in explicit:
        return explicit[text]
    if published_at and measured_at:
        try:
            published = datetime.fromisoformat(published_at)
            measured = datetime.fromisoformat(measured_at)
            elapsed = max(0.0, (measured - published).total_seconds() / 3600.0)
            closest = min(MEASUREMENT_WINDOWS, key=lambda hours: abs(hours - elapsed))
            if abs(closest - elapsed) <= WINDOW_TOLERANCE_HOURS[closest]:
                return f"{closest}h"
        except (TypeError, ValueError):
            pass
    return f"custom:{measured_at}" if measured_at else "custom"


def _normalized_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return {_key(key): item for key, item in (value or {}).items()}


def _pick(
    raw: Mapping[str, Any],
    defaults: Mapping[str, Any],
    *aliases: str,
) -> Any:
    for alias in aliases:
        key = _key(alias)
        if key in raw and _text(raw[key]):
            return raw[key]
    for alias in aliases:
        key = _key(alias)
        if key in defaults and _text(defaults[key]):
            return defaults[key]
    return ""


def normalize_performance_record(
    value: Mapping[str, Any],
    *,
    defaults: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Metric row must be an object")
    raw = _normalized_mapping(value)
    fallback = _normalized_mapping(defaults)
    current_time = now or datetime.now(timezone.utc)

    video_id = _text(_pick(raw, fallback, "video_id", "item_id", "video id", "id video"))
    channel_id = _text(_pick(
        raw, fallback, "channel_id", "tiktok_id", "account", "username", "kenh",
    )).lstrip("@")
    if not video_id:
        raise ValueError("MISSING_VIDEO_ID")
    if not channel_id:
        raise ValueError("MISSING_CHANNEL_ID")

    measured_at = _datetime(
        _pick(raw, fallback, "measured_at", "snapshot_at", "collected_at", "ngay_do"),
        default=current_time,
    )
    if not measured_at:
        raise ValueError("INVALID_MEASURED_AT")
    published_at = _datetime(_pick(
        raw, fallback, "published_at", "posted_at", "publish_time", "ngay_dang",
    ))
    source_url = _text(_pick(raw, fallback, "source_url", "video_url", "url", "link"))
    source_domain = _text(_pick(raw, fallback, "source_domain", "domain"))
    if not source_domain and source_url:
        source_domain = urlsplit(source_url).netloc.lower().removeprefix("www.")
    views = int(parse_number(_pick(
        raw, fallback, "views", "video_views", "view_count", "luot_xem",
    )))
    retention_2s = parse_number(_pick(
        raw, fallback, "retention_2s", "retention_2_sec", "2s_retention",
        "giu chan 2 giay",
    ), rate=True)
    retention_6s = parse_number(_pick(
        raw, fallback, "retention_6s", "retention_6_sec", "6s_retention",
        "giu chan 6 giay",
    ), rate=True)
    if views > 0:
        if retention_2s <= 0:
            retention_2s = parse_number(_pick(
                raw, fallback, "2-second video views", "2 second video views",
                "2s views", "luot xem 2 giay",
            )) / views
        if retention_6s <= 0:
            retention_6s = parse_number(_pick(
                raw, fallback, "6-second video views", "6 second video views",
                "6s views", "luot xem 6 giay",
            )) / views

    record = {
        "video_id": video_id,
        "channel_id": channel_id,
        "source_type": _text(_pick(raw, fallback, "source_type")) or "tiktok",
        "source_url": source_url,
        "source_domain": source_domain,
        "title": _text(_pick(raw, fallback, "title", "video_title", "caption", "tieu_de")),
        "story_type": _text(_pick(raw, fallback, "story_type")) or "unknown",
        "hook_type": _text(_pick(raw, fallback, "hook_type")) or "unknown",
        "duration": parse_number(_pick(
            raw, fallback, "duration", "video_duration", "duration_seconds", "thoi_luong",
        )),
        "music_mood": _text(_pick(raw, fallback, "music_mood")) or "unknown",
        "music_energy": int(parse_number(_pick(
            raw, fallback, "music_energy", "energy", "do_manh_nhac",
        ))),
        "subtitle_style": _text(_pick(
            raw, fallback, "subtitle_style", "subtitle_variant", "kieu_phu_de",
        )) or "unknown",
        "cta_mode": _text(_pick(
            raw, fallback, "cta_mode", "cta_variant", "kieu_cta",
        )) or "unknown",
        "visual_beat_count": int(parse_number(_pick(
            raw, fallback, "visual_beat_count", "beat_count", "beats", "so_beat",
        ))),
        "experiment_id": _text(_pick(
            raw, fallback, "experiment_id", "test_id", "ab_test_id",
        )),
        "experiment_variant": _text(_pick(
            raw, fallback, "experiment_variant", "variant", "test_variant", "nhanh_thu_nghiem",
        )),
        "experiment_variable": _text(_pick(
            raw, fallback, "experiment_variable", "test_variable", "bien_thu_nghiem",
        )),
        "experiment_value": _text(_pick(
            raw, fallback, "experiment_value", "test_value", "gia_tri_thu_nghiem",
        )),
        "views": views,
        "average_watch_time": parse_number(_pick(
            raw, fallback, "average_watch_time", "avg_watch_time", "watch_time",
            "average watch duration", "avg watch duration",
            "thoi_gian_xem_trung_binh", "thoi_gian_xem_trung_binh_giay",
        )),
        "watched_full_rate": min(1.0, parse_number(_pick(
            raw, fallback, "watched_full_rate", "completion_rate",
            "watched_full_video", "watched full video rate", "ty_le_xem_het",
        ), rate=True)),
        "retention_2s": min(1.0, max(0.0, retention_2s)),
        "retention_6s": min(1.0, max(0.0, retention_6s)),
        "likes": int(parse_number(_pick(raw, fallback, "likes", "like_count", "luot_thich"))),
        "comments": int(parse_number(_pick(raw, fallback, "comments", "comment_count", "binh_luan"))),
        "shares": int(parse_number(_pick(raw, fallback, "shares", "share_count", "luot_chia_se"))),
        "saves": int(parse_number(_pick(raw, fallback, "saves", "save_count", "favorites", "luot_luu"))),
        "follows": int(parse_number(_pick(raw, fallback, "follows", "new_followers", "followers_gained", "luot_theo_doi"))),
        "published_at": published_at,
        "measured_at": measured_at,
        "import_source": _text(_pick(raw, fallback, "import_source", "source_file")),
    }
    record["measurement_window"] = normalize_measurement_window(
        _pick(raw, fallback, "measurement_window", "window", "measurement_hour", "moc_do"),
        published_at=published_at,
        measured_at=measured_at,
    )
    record["snapshot_key"] = "|".join((
        channel_id.lower(), video_id, record["measurement_window"],
    ))
    return record


def latest_snapshots(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for item in records:
        record = dict(item)
        key = (str(record.get("channel_id", "")), str(record.get("video_id", "")))
        existing = latest.get(key)
        if existing is None or str(record.get("measured_at", "")) >= str(existing.get("measured_at", "")):
            latest[key] = record
    return list(latest.values())


def _median(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(clean) if clean else 0.0


def _watch_percentage(item: Mapping[str, Any]) -> float | None:
    duration = float(item.get("duration", 0) or 0)
    if duration <= 0:
        return None
    return float(item.get("average_watch_time", 0) or 0) / duration * 100.0


def _retention_drop_2s_to_6s(item: Mapping[str, Any]) -> float:
    retention_2s = float(item.get("retention_2s", 0) or 0)
    retention_6s = float(item.get("retention_6s", 0) or 0)
    return (retention_2s - retention_6s) * 100.0


def aggregate_performance(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in records]
    total_views = sum(int(item.get("views", 0) or 0) for item in rows)

    def per_1000(field: str) -> float:
        total = sum(int(item.get(field, 0) or 0) for item in rows)
        return (total / total_views * 1000.0) if total_views else 0.0

    watch_percentages = [
        percentage for item in rows
        if float(item.get("average_watch_time", 0) or 0) > 0
        and (percentage := _watch_percentage(item)) is not None
    ]
    watch_time_rows = [
        item for item in rows
        if float(item.get("average_watch_time", 0) or 0) > 0
    ]
    completion_rows = [
        item for item in rows
        if float(item.get("watched_full_rate", 0) or 0) > 0
    ]
    watch_time_views = sum(
        int(item.get("views", 0) or 0)
        for item in rows
        if float(item.get("average_watch_time", 0) or 0) > 0
    )
    weighted_watch_time = (
        sum(
            float(item.get("average_watch_time", 0) or 0)
            * int(item.get("views", 0) or 0)
            for item in rows
        ) / total_views
        if total_views else 0.0
    )
    duration_views = sum(
        int(item.get("views", 0) or 0)
        for item in rows
        if float(item.get("duration", 0) or 0) > 0
    )
    weighted_watch_percentage = (
        sum(
            (_watch_percentage(item) or 0.0) * int(item.get("views", 0) or 0)
            for item in rows
            if _watch_percentage(item) is not None
        ) / duration_views
        if duration_views else 0.0
    )
    retention_rows = [
        item for item in rows
        if float(item.get("retention_2s", 0) or 0) > 0
        or float(item.get("retention_6s", 0) or 0) > 0
    ]
    measured_values = [str(item.get("measured_at", "")) for item in rows if item.get("measured_at")]
    result = {
        "sample_size": len(rows),
        "total_views": total_views,
        "median_views": round(_median(item.get("views", 0) for item in rows), 3),
        "median_average_watch_time": round(_median(
            item.get("average_watch_time", 0) for item in watch_time_rows
        ), 3),
        "median_watch_percentage": round(_median(watch_percentages), 3),
        "weighted_average_watch_time": round(weighted_watch_time, 3),
        "weighted_watch_percentage": round(weighted_watch_percentage, 3),
        "median_watched_full_rate": round(_median(
            float(item.get("watched_full_rate", 0) or 0) * 100.0 for item in completion_rows
        ), 3),
        "median_retention_2s": round(_median(
            float(item.get("retention_2s", 0) or 0) * 100.0 for item in retention_rows
        ), 3),
        "median_retention_6s": round(_median(
            float(item.get("retention_6s", 0) or 0) * 100.0 for item in retention_rows
        ), 3),
        "median_retention_drop_2s_to_6s": round(_median(
            _retention_drop_2s_to_6s(item) for item in retention_rows
        ), 3),
        "likes_per_1000": round(per_1000("likes"), 3),
        "comments_per_1000": round(per_1000("comments"), 3),
        "shares_per_1000": round(per_1000("shares"), 3),
        "saves_per_1000": round(per_1000("saves"), 3),
        "follows_per_1000": round(per_1000("follows"), 3),
        "measured_from": min(measured_values) if measured_values else "",
        "measured_to": max(measured_values) if measured_values else "",
        "data_quality": {
            "with_duration": sum(float(item.get("duration", 0) or 0) > 0 for item in rows),
            "with_watch_time": sum(float(item.get("average_watch_time", 0) or 0) > 0 for item in rows),
            "watch_time_view_coverage": round(
                watch_time_views / total_views * 100.0 if total_views else 0.0,
                3,
            ),
            "with_completion": sum(float(item.get("watched_full_rate", 0) or 0) > 0 for item in rows),
            "with_retention_2s": sum(float(item.get("retention_2s", 0) or 0) > 0 for item in rows),
            "with_retention_6s": sum(float(item.get("retention_6s", 0) or 0) > 0 for item in rows),
        },
    }
    engagement_total = sum(
        int(item.get(field, 0) or 0)
        for item in rows
        for field in ("likes", "comments", "shares", "saves")
    )
    result["engagements_per_1000"] = round(
        engagement_total / total_views * 1000.0 if total_views else 0.0, 3
    )
    return result


def _duration_bucket(value: Any) -> str:
    duration = parse_number(value)
    if duration <= 0:
        return "unknown"
    if duration < 20:
        return "<20s"
    if duration < 25:
        return "20-24s"
    if duration < 30:
        return "25-29s"
    if duration < 40:
        return "30-39s"
    return "40s+"


def _breakdown(
    records: list[dict[str, Any]],
    field: str,
    *,
    min_samples: int,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        value = _duration_bucket(record.get("duration")) if field == "duration" else str(record.get(field) or "unknown")
        groups.setdefault(value, []).append(record)
    result = []
    for value, group in groups.items():
        summary = aggregate_performance(group)
        summary.update({"value": value, "eligible": len(group) >= min_samples})
        result.append(summary)
    return sorted(result, key=lambda item: (-item["sample_size"], -item["total_views"], item["value"]))


def find_snapshot_anomalies(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in records:
        record = dict(item)
        key = (str(record.get("channel_id", "")), str(record.get("video_id", "")))
        groups.setdefault(key, []).append(record)
    anomalies: list[dict[str, Any]] = []
    cumulative_fields = ("views", "likes", "comments", "shares", "saves", "follows")
    for (channel_id, video_id), snapshots in groups.items():
        ordered = sorted(snapshots, key=lambda item: str(item.get("measured_at", "")))
        for previous, current in zip(ordered, ordered[1:]):
            for field in cumulative_fields:
                old_value = int(previous.get(field, 0) or 0)
                new_value = int(current.get(field, 0) or 0)
                if new_value < old_value:
                    anomalies.append({
                        "channel_id": channel_id,
                        "video_id": video_id,
                        "error_code": f"NON_MONOTONIC_{field.upper()}",
                        "previous": old_value,
                        "current": new_value,
                        "previous_measured_at": previous.get("measured_at", ""),
                        "current_measured_at": current.get("measured_at", ""),
                    })
        for snapshot in ordered:
            retention_2s = float(snapshot.get("retention_2s", 0) or 0)
            retention_6s = float(snapshot.get("retention_6s", 0) or 0)
            if retention_6s > retention_2s + 1e-6:
                anomalies.append({
                    "channel_id": channel_id,
                    "video_id": video_id,
                    "error_code": "RETENTION_6S_GT_2S",
                    "retention_2s": retention_2s,
                    "retention_6s": retention_6s,
                    "measured_at": snapshot.get("measured_at", ""),
                })
    return anomalies[:100]


def analyze_performance(
    records: Iterable[Mapping[str, Any]],
    *,
    min_samples: int = 30,
    latest_only: bool = True,
) -> dict[str, Any]:
    rows = [dict(item) for item in records]
    analyzed = latest_snapshots(rows) if latest_only else rows
    minimum = max(1, int(min_samples))
    overview = aggregate_performance(analyzed)
    overview["eligible"] = overview["sample_size"] >= minimum
    return {
        "status": "ready" if overview["eligible"] else "insufficient_sample",
        "overview": overview,
        "minimum_sample_size": minimum,
        "latest_only": bool(latest_only),
        "snapshot_anomalies": find_snapshot_anomalies(rows),
        "breakdowns": {
            field: _breakdown(analyzed, field, min_samples=minimum)
            for field in (
                "channel_id", "story_type", "hook_type", "duration",
                "music_mood", "music_energy", "subtitle_style", "cta_mode",
                "experiment_id", "experiment_variant", "measurement_window",
            )
        },
    }
