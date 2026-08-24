"""Build conservative, operator-approved learning for each TikTok channel."""

from __future__ import annotations

import json
import math
import os
import statistics
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from shared.core.performance_analyzer import (
    aggregate_performance,
    latest_snapshots,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CHANNEL_LEARNING_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "channel_learning.json",
)
LEARNING_VERSION = 1
_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_channel_id(value: Any) -> str:
    return str(value or "").replace("@", "").strip()


def _median(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    return statistics.median(clean) if clean else 0.0


def _per_1000(row: Mapping[str, Any], field: str) -> float:
    views = max(0, int(row.get("views", 0) or 0))
    if not views:
        return 0.0
    value = max(0, int(row.get(field, 0) or 0)) / views * 1000.0
    return min(150.0, value)


def _row_score(row: Mapping[str, Any]) -> float | None:
    """Balanced per-video score; caps protect the median from tiny-view ratios."""
    duration = float(row.get("duration", 0) or 0)
    views = int(row.get("views", 0) or 0)
    if duration <= 0 or views <= 0:
        return None
    watch_percentage = min(
        120.0,
        max(0.0, float(row.get("average_watch_time", 0) or 0) / duration * 100.0),
    )
    completion = min(100.0, max(0.0, float(row.get("watched_full_rate", 0) or 0) * 100.0))
    retention_6s = min(100.0, max(0.0, float(row.get("retention_6s", 0) or 0) * 100.0))
    return (
        watch_percentage * 0.35
        + completion * 0.25
        + retention_6s * 0.20
        + _per_1000(row, "shares") * 0.08
        + _per_1000(row, "saves") * 0.07
        + _per_1000(row, "follows") * 0.05
    )


def _duration_bucket(value: Any) -> tuple[str, list[int]]:
    duration = float(value or 0)
    if duration < 20:
        return "under_20s", [10, 19]
    if duration < 25:
        return "20_24s", [20, 24]
    if duration < 30:
        return "25_29s", [25, 29]
    if duration < 40:
        return "30_39s", [30, 39]
    return "40s_plus", [40, 60]


def _rank_within_story(
    rows: list[dict[str, Any]],
    field: str,
    *,
    minimum_group_size: int,
) -> list[dict[str, Any]]:
    tagged_rows = []
    ranges: dict[str, list[int]] = {}
    for row in rows:
        if field == "duration":
            value, duration_range = _duration_bucket(row.get("duration"))
            ranges[value] = duration_range
        else:
            value = str(row.get(field) or "unknown").strip().lower()
        if not value or value == "unknown":
            continue
        tagged_rows.append((row, value))

    minimum_cell_size = max(2, minimum_group_size // 2)
    story_counts: dict[str, dict[str, int]] = {}
    for row, value in tagged_rows:
        story_type = str(row.get("story_type") or "unknown")
        story_counts.setdefault(story_type, {}).setdefault(value, 0)
        story_counts[story_type][value] += 1
    comparable_values = {
        story_type: {
            value for value, count in counts.items()
            if count >= minimum_cell_size
        }
        for story_type, counts in story_counts.items()
    }
    comparable_values = {
        story_type: values for story_type, values in comparable_values.items()
        if len(values) >= 2
    }
    comparable_rows = [
        (row, value) for row, value in tagged_rows
        if value in comparable_values.get(
            str(row.get("story_type") or "unknown"),
            set(),
        )
    ]
    story_baselines: dict[str, float] = {}
    for story_type in comparable_values:
        story_baselines[story_type] = _median(
            row["_learning_score"] for row, _value in comparable_rows
            if str(row.get("story_type") or "unknown") == story_type
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for row, value in comparable_rows:
        groups.setdefault(value, []).append(row)

    ranked = []
    for value, group in groups.items():
        if len(group) < minimum_group_size:
            continue
        relative = [
            float(row["_learning_score"])
            - story_baselines[str(row.get("story_type") or "unknown")]
            for row in group
        ]
        summary = aggregate_performance(group)
        ranked.append({
            "value": value,
            "sample_size": len(group),
            "median_learning_score": round(_median(
                row["_learning_score"] for row in group
            ), 3),
            "median_relative_to_story_type": round(_median(relative), 3),
            "median_watch_percentage": summary["median_watch_percentage"],
            "median_watched_full_rate": summary["median_watched_full_rate"],
            "shares_per_1000": summary["shares_per_1000"],
            "saves_per_1000": summary["saves_per_1000"],
            "follows_per_1000": summary["follows_per_1000"],
            **({"duration_range": ranges[value]} if field == "duration" else {}),
        })
    return sorted(
        ranked,
        key=lambda item: (
            -item["median_relative_to_story_type"],
            -item["sample_size"],
            item["value"],
        ),
    )


def _rank_story_types(
    rows: list[dict[str, Any]],
    *,
    minimum_group_size: int,
) -> list[dict[str, Any]]:
    channel_baseline = _median(row["_learning_score"] for row in rows)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = str(row.get("story_type") or "unknown").strip().lower()
        if value != "unknown":
            groups.setdefault(value, []).append(row)
    ranked = []
    for value, group in groups.items():
        if len(group) < minimum_group_size:
            continue
        score = _median(row["_learning_score"] for row in group)
        summary = aggregate_performance(group)
        ranked.append({
            "value": value,
            "sample_size": len(group),
            "median_learning_score": round(score, 3),
            "median_relative_to_channel": round(score - channel_baseline, 3),
            "median_watch_percentage": summary["median_watch_percentage"],
            "median_watched_full_rate": summary["median_watched_full_rate"],
            "shares_per_1000": summary["shares_per_1000"],
            "saves_per_1000": summary["saves_per_1000"],
            "follows_per_1000": summary["follows_per_1000"],
        })
    return sorted(
        ranked,
        key=lambda item: (
            -item["median_relative_to_channel"],
            -item["sample_size"],
            item["value"],
        ),
    )


def _positive_values(items: list[dict[str, Any]], relative_field: str) -> list[str]:
    positive = [item["value"] for item in items if item[relative_field] > 0]
    return positive[:2]


def _prompt_lessons(learning: Mapping[str, Any]) -> list[str]:
    lessons = []
    hooks = learning.get("winning_hook_types") or []
    stories = learning.get("winning_story_types") or []
    duration_range = learning.get("best_duration_range") or []
    moods = learning.get("winning_music_moods") or []
    weak_patterns = learning.get("weak_patterns") or []
    if hooks:
        lessons.append(
            "Ưu tiên hook type đã có median tốt hơn trong cùng story type: "
            + ", ".join(hooks)
            + "."
        )
    if stories:
        lessons.append(
            "Nhóm nội dung đang có tín hiệu tốt hơn trong kênh: "
            + ", ".join(stories)
            + "."
        )
    if len(duration_range) == 2:
        lessons.append(
            "Khoảng thời lượng đang có tín hiệu tốt: "
            f"{duration_range[0]}-{duration_range[1]} giây."
        )
    if moods:
        lessons.append("Music mood đang có tín hiệu tốt: " + ", ".join(moods) + ".")
    lessons.extend(str(item) for item in weak_patterns[:3])
    return lessons


def build_channel_learning(
    records: Iterable[Mapping[str, Any]],
    channel_id: str,
    *,
    minimum_sample_size: int = 30,
    minimum_group_size: int = 5,
) -> dict[str, Any]:
    """Learn from latest snapshots without allowing one viral video to decide."""
    clean_channel = _clean_channel_id(channel_id)
    minimum_sample = max(1, int(minimum_sample_size))
    minimum_group = max(2, int(minimum_group_size))
    latest = latest_snapshots([
        dict(item) for item in records
        if _clean_channel_id(item.get("channel_id")).lower() == clean_channel.lower()
    ])
    usable = []
    for row in latest:
        score = _row_score(row)
        if score is None:
            continue
        enriched = dict(row)
        enriched["_learning_score"] = score
        usable.append(enriched)

    base = {
        "learning_version": LEARNING_VERSION,
        "channel_id": clean_channel,
        "enabled": False,
        "status": "ready" if len(usable) >= minimum_sample else "insufficient_sample",
        "sample_size": len(latest),
        "usable_sample_size": len(usable),
        "minimum_sample_size": minimum_sample,
        "minimum_group_size": minimum_group,
        "generated_at": _utc_now(),
        "winning_hook_types": [],
        "winning_story_types": [],
        "best_duration_range": [],
        "winning_music_moods": [],
        "weak_patterns": [],
        "prompt_lessons": [],
        "analysis": {},
        "method": (
            "latest snapshot/video; median metrics; engagement per 1,000 views; "
            "hook/duration/music normalized inside story_type"
        ),
    }
    if base["status"] != "ready":
        return base

    hook_ranking = _rank_within_story(
        usable, "hook_type", minimum_group_size=minimum_group,
    )
    duration_ranking = _rank_within_story(
        usable, "duration", minimum_group_size=minimum_group,
    )
    music_ranking = _rank_within_story(
        usable, "music_mood", minimum_group_size=minimum_group,
    )
    story_ranking = _rank_story_types(usable, minimum_group_size=minimum_group)
    base["winning_hook_types"] = _positive_values(
        hook_ranking, "median_relative_to_story_type",
    )
    base["winning_story_types"] = _positive_values(
        story_ranking, "median_relative_to_channel",
    )
    if duration_ranking and duration_ranking[0]["median_relative_to_story_type"] > 0:
        base["best_duration_range"] = duration_ranking[0]["duration_range"]
    base["winning_music_moods"] = _positive_values(
        music_ranking, "median_relative_to_story_type",
    )

    weak_patterns = []
    if hook_ranking and hook_ranking[-1]["median_relative_to_story_type"] < -3:
        weak_patterns.append(
            f"Hạn chế hook_type '{hook_ranking[-1]['value']}': median thấp hơn "
            "baseline của cùng story type."
        )
    if story_ranking and story_ranking[-1]["median_relative_to_channel"] < -3:
        weak_patterns.append(
            f"Cân nhắc kỹ story_type '{story_ranking[-1]['value']}': median thấp hơn "
            "baseline của kênh."
        )
    base["weak_patterns"] = weak_patterns
    base["analysis"] = {
        "overview": aggregate_performance(usable),
        "hook_type": hook_ranking,
        "story_type": story_ranking,
        "duration": duration_ranking,
        "music_mood": music_ranking,
    }
    base["prompt_lessons"] = _prompt_lessons(base)
    return base


class ChannelLearningStore:
    """Atomic runtime store with explicit operator enable/disable/delete controls."""

    def __init__(self, path: str = DEFAULT_CHANNEL_LEARNING_PATH):
        self.path = os.path.abspath(path)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, Mapping):
            raise ValueError("INVALID_CHANNEL_LEARNING_STORE")
        return {
            str(channel_id): dict(item)
            for channel_id, item in payload.items()
            if isinstance(item, Mapping)
        }

    def _write(self, payload: Mapping[str, Mapping[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary_path = f"{self.path}.tmp.{os.getpid()}.{threading.get_ident()}"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, self.path)

    def list(self) -> dict[str, dict[str, Any]]:
        with _LOCK:
            return deepcopy(self._read())

    def get(self, channel_id: str) -> dict[str, Any] | None:
        target = _clean_channel_id(channel_id).lower()
        return next((
            deepcopy(item) for key, item in self.list().items()
            if _clean_channel_id(key).lower() == target
        ), None)

    def upsert(
        self,
        learning: Mapping[str, Any],
        *,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        channel_id = _clean_channel_id(learning.get("channel_id"))
        if not channel_id:
            raise ValueError("MISSING_LEARNING_CHANNEL")
        with _LOCK:
            payload = self._read()
            existing_key = next((
                key for key in payload if _clean_channel_id(key).lower() == channel_id.lower()
            ), channel_id)
            previous = payload.get(existing_key, {})
            item = deepcopy(dict(learning))
            requested_enabled = previous.get("enabled", False) if enabled is None else bool(enabled)
            usable_sample_size = int(item.get("usable_sample_size", 0) or 0)
            if enabled is True and usable_sample_size < 30:
                raise ValueError("CHANNEL_LEARNING_REQUIRES_30_VIDEOS")
            item["enabled"] = bool(
                requested_enabled
                and item.get("status") == "ready"
                and usable_sample_size >= 30
            )
            item["channel_id"] = channel_id
            item["updated_at"] = _utc_now()
            payload[existing_key] = item
            self._write(payload)
        return deepcopy(item)

    def set_enabled(self, channel_id: str, enabled: bool) -> dict[str, Any]:
        item = self.get(channel_id)
        if not item:
            raise ValueError("CHANNEL_LEARNING_NOT_FOUND")
        if enabled and item.get("status") != "ready":
            raise ValueError("CHANNEL_LEARNING_NOT_READY")
        if enabled and int(item.get("usable_sample_size", 0) or 0) < 30:
            raise ValueError("CHANNEL_LEARNING_REQUIRES_30_VIDEOS")
        return self.upsert(item, enabled=enabled)

    def delete(self, channel_id: str) -> bool:
        target = _clean_channel_id(channel_id).lower()
        with _LOCK:
            payload = self._read()
            keys = [key for key in payload if _clean_channel_id(key).lower() == target]
            if not keys:
                return False
            for key in keys:
                payload.pop(key, None)
            self._write(payload)
        return True


def performance_learning_enabled(value: bool | None = None) -> bool:
    if value is not None:
        return bool(value)
    return str(os.environ.get("PERFORMANCE_LEARNING_ENABLED", "")).strip().lower() in {
        "1", "true", "yes", "on", "enabled",
    }


def load_prompt_learning(
    channel_id: str,
    *,
    path: str = DEFAULT_CHANNEL_LEARNING_PATH,
    enabled: bool | None = None,
) -> list[str]:
    if not performance_learning_enabled(enabled) or not os.path.exists(path):
        return []
    learning = ChannelLearningStore(path).get(channel_id)
    if (
        not learning
        or not learning.get("enabled")
        or learning.get("status") != "ready"
        or int(learning.get("usable_sample_size", 0) or 0) < 30
    ):
        return []
    return [str(item) for item in learning.get("prompt_lessons", []) if str(item).strip()]
