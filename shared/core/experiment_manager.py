"""Controlled, single-variable experiments for short-form video production."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
DEFAULT_EXPERIMENTS_PATH = os.path.join(PROJECT_ROOT, "data", "experiments.json")
EXPERIMENT_STORE_VERSION = 1
RUNNING_STATUS = "running"
EXPERIMENT_STATUSES = {"draft", RUNNING_STATUS, "paused", "completed"}
EXPERIMENT_SOURCE_TYPES = {"article", "facebook", "tiktok", "video"}
PRIMARY_METRICS = {
    "median_watch_percentage",
    "median_watched_full_rate",
    "median_retention_2s",
    "median_retention_6s",
    "median_retention_drop_2s_to_6s",
    "shares_per_1000",
    "saves_per_1000",
    "follows_per_1000",
    "engagements_per_1000",
}
LOWER_IS_BETTER_METRICS = {
    "median_retention_drop_2s_to_6s",
}

EXPERIMENT_VARIABLES: dict[str, dict[str, Any]] = {
    "hook_type": {"values": {"result", "conflict", "impact"}},
    "target_duration_seconds": {"minimum": 10, "maximum": 60},
    "subtitle_style": {"values": {"normal", "keyword_highlight"}},
    "visual_beat_count": {"minimum": 3, "maximum": 12},
    "cta_mode": {"values": {"none", "specific"}},
    "music_energy": {"minimum": 1, "maximum": 3},
}

_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_channel_id(value: Any) -> str:
    return str(value or "").replace("@", "").strip()


def _clean_source_types(value: Any) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    normalized = sorted({
        str(item).strip().lower() for item in items if str(item).strip()
    })
    unsupported = [item for item in normalized if item not in EXPERIMENT_SOURCE_TYPES]
    if unsupported:
        raise ValueError("INVALID_EXPERIMENT_SOURCE_TYPE:" + ",".join(unsupported))
    return normalized


def _normalize_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError as error:
        raise ValueError("INVALID_EXPERIMENT_DATETIME") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _validate_change(variable: str, value: Any) -> Any:
    rule = EXPERIMENT_VARIABLES[variable]
    if "values" in rule:
        normalized = str(value).strip().lower()
        if normalized not in rule["values"]:
            allowed = ", ".join(sorted(rule["values"]))
            raise ValueError(f"INVALID_EXPERIMENT_VALUE:{variable}; allowed={allowed}")
        return normalized
    try:
        normalized_number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"INVALID_EXPERIMENT_VALUE:{variable}") from error
    if not rule["minimum"] <= normalized_number <= rule["maximum"]:
        raise ValueError(
            f"INVALID_EXPERIMENT_VALUE:{variable}; "
            f"range={rule['minimum']}-{rule['maximum']}"
        )
    return normalized_number


def normalize_experiment(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an A/B definition and prove both arms change one variable only."""
    if not isinstance(value, Mapping):
        raise ValueError("EXPERIMENT_MUST_BE_OBJECT")
    experiment_id = str(value.get("experiment_id") or value.get("id") or "").strip()
    if not experiment_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,79}", experiment_id):
        raise ValueError("INVALID_EXPERIMENT_ID")
    channel_id = _clean_channel_id(value.get("channel_id"))
    if not channel_id:
        raise ValueError("MISSING_EXPERIMENT_CHANNEL")
    status = str(value.get("status") or "draft").strip().lower()
    if status not in EXPERIMENT_STATUSES:
        raise ValueError("INVALID_EXPERIMENT_STATUS")

    variants = value.get("variants")
    if not isinstance(variants, list) or len(variants) != 2:
        raise ValueError("EXPERIMENT_REQUIRES_EXACTLY_TWO_VARIANTS")
    normalized_variants = []
    variables = set()
    names = set()
    values = []
    for index, raw_variant in enumerate(variants):
        if not isinstance(raw_variant, Mapping):
            raise ValueError("INVALID_EXPERIMENT_VARIANT")
        name = str(raw_variant.get("name") or ("control" if index == 0 else "variant")).strip()
        if not name or name in names:
            raise ValueError("DUPLICATE_EXPERIMENT_VARIANT")
        names.add(name)
        changes = raw_variant.get("changes")
        if not isinstance(changes, Mapping) or len(changes) != 1:
            raise ValueError("EACH_VARIANT_MUST_CHANGE_EXACTLY_ONE_VARIABLE")
        variable, raw_change = next(iter(changes.items()))
        variable = str(variable).strip()
        if variable not in EXPERIMENT_VARIABLES:
            raise ValueError(f"UNSUPPORTED_EXPERIMENT_VARIABLE:{variable}")
        variables.add(variable)
        normalized_change = _validate_change(variable, raw_change)
        values.append(normalized_change)
        try:
            weight = int(raw_variant.get("weight", 50))
        except (TypeError, ValueError) as error:
            raise ValueError("INVALID_EXPERIMENT_WEIGHT") from error
        if weight <= 0:
            raise ValueError("INVALID_EXPERIMENT_WEIGHT")
        normalized_variants.append({
            "name": name,
            "changes": {variable: normalized_change},
            "weight": weight,
        })
    if len(variables) != 1:
        raise ValueError("EXPERIMENT_VARIANTS_MUST_CHANGE_THE_SAME_VARIABLE")
    if values[0] == values[1]:
        raise ValueError("EXPERIMENT_VARIANTS_MUST_HAVE_DISTINCT_VALUES")

    primary_metric = str(
        value.get("primary_metric") or "median_watch_percentage"
    ).strip()
    if primary_metric not in PRIMARY_METRICS:
        raise ValueError("INVALID_EXPERIMENT_PRIMARY_METRIC")
    try:
        minimum_sample_size = max(30, int(value.get("minimum_sample_size", 30)))
    except (TypeError, ValueError) as error:
        raise ValueError("INVALID_EXPERIMENT_MINIMUM_SAMPLE") from error

    created_at = str(value.get("created_at") or _utc_now())
    updated_at = str(value.get("updated_at") or created_at)
    starts_at = _normalize_datetime(value.get("starts_at"))
    ends_at = _normalize_datetime(value.get("ends_at"))
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValueError("EXPERIMENT_END_MUST_BE_AFTER_START")
    return {
        "experiment_id": experiment_id,
        "name": str(value.get("name") or experiment_id).strip(),
        "channel_id": channel_id,
        "status": status,
        "variable": next(iter(variables)),
        "variants": normalized_variants,
        "primary_metric": primary_metric,
        "minimum_sample_size": minimum_sample_size,
        "source_types": _clean_source_types(value.get("source_types")),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "operator_notes": str(value.get("operator_notes") or "").strip(),
    }


def _in_active_window(experiment: Mapping[str, Any], now: str) -> bool:
    starts_at = str(experiment.get("starts_at") or "")
    ends_at = str(experiment.get("ends_at") or "")
    return (not starts_at or starts_at <= now) and (not ends_at or now < ends_at)


def assign_experiment(
    experiment: Mapping[str, Any],
    content_key: str,
) -> dict[str, Any]:
    """Deterministically assign the same source to the same experiment arm."""
    normalized = normalize_experiment(experiment)
    stable_key = str(content_key or "").strip()
    if not stable_key:
        raise ValueError("MISSING_EXPERIMENT_CONTENT_KEY")
    variants = normalized["variants"]
    total_weight = sum(item["weight"] for item in variants)
    assignment_key = (
        f"{normalized['experiment_id']}|"
        f"{normalized['channel_id'].lower()}|{stable_key}"
    )
    digest = hashlib.blake2b(
        assignment_key.encode("utf-8"),
        digest_size=8,
    ).digest()
    bucket = int.from_bytes(digest, "big") % total_weight
    cursor = 0
    selected = variants[-1]
    for variant in variants:
        cursor += variant["weight"]
        if bucket < cursor:
            selected = variant
            break
    variable, selected_value = next(iter(selected["changes"].items()))
    return {
        "experiment_id": normalized["experiment_id"],
        "experiment_variant": selected["name"],
        "experiment_variable": variable,
        "experiment_value": selected_value,
        "channel_id": normalized["channel_id"],
        "content_key": stable_key,
    }


def experiment_instruction(assignment: Mapping[str, Any]) -> str:
    variable = str(assignment.get("experiment_variable") or "")
    value = assignment.get("experiment_value")
    instructions = {
        "hook_type": (
            f"Chọn selected_hook thuộc hook_type='{value}'. "
            "Vẫn tạo đủ ba hook variants, "
            "nhưng chỉ biến lựa chọn hook được phép thay đổi."
        ),
        "target_duration_seconds": (
            f"Viết tổng hook + script_voice cho thời lượng mục tiêu {value} giây; "
            "không đổi tone, hook type hoặc phong cách hình vì thử nghiệm này."
        ),
        "subtitle_style": (
            f"Đặt subtitle_style='{value}'. Không đổi hook, độ dài hoặc nhạc "
            "vì thử nghiệm này."
        ),
        "visual_beat_count": (
            f"Tạo đúng {value} beats có nội dung thực; không kéo dài hoặc "
            "chia câu giả để đủ số."
        ),
        "cta_mode": (
            "Không thêm CTA vào hook hoặc script_voice."
            if value == "none"
            else (
                "Thêm đúng một CTA cụ thể, gắn trực tiếp với chi tiết "
                "trong nội dung."
            )
        ),
        "music_energy": (
            f"Đặt music_energy={value}; quy tắc an toàn cho nội dung "
            "nhạy cảm vẫn có ưu tiên cao hơn."
        ),
    }
    if variable not in instructions:
        raise ValueError(f"UNSUPPORTED_EXPERIMENT_VARIABLE:{variable}")
    return instructions[variable]


def apply_experiment_metadata(
    content: Mapping[str, Any] | None,
    assignment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = dict(content or {})
    if not assignment:
        return result
    for key in (
        "experiment_id", "experiment_variant", "experiment_variable",
        "experiment_value",
    ):
        result[key] = assignment.get(key, "")
    return result


def _enabled(value: bool | None, environment_name: str) -> bool:
    if value is not None:
        return bool(value)
    return str(os.environ.get(environment_name, "")).strip().lower() in {
        "1", "true", "yes", "on", "enabled",
    }


class ExperimentManager:
    """Atomic JSON registry; only one running experiment is allowed per channel."""

    def __init__(self, path: str = DEFAULT_EXPERIMENTS_PATH):
        self.path = os.path.abspath(path)

    def _read(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        experiments = payload.get("experiments", []) if isinstance(payload, Mapping) else []
        if not isinstance(experiments, list):
            raise ValueError("INVALID_EXPERIMENT_STORE")
        return [normalize_experiment(item) for item in experiments]

    def _write(self, experiments: Iterable[Mapping[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "version": EXPERIMENT_STORE_VERSION,
            "experiments": [deepcopy(dict(item)) for item in experiments],
        }
        temporary_path = f"{self.path}.tmp.{os.getpid()}.{threading.get_ident()}"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, self.path)

    def list(self) -> list[dict[str, Any]]:
        with _LOCK:
            return deepcopy(self._read())

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        target = str(experiment_id or "").strip()
        return next((item for item in self.list() if item["experiment_id"] == target), None)

    def upsert(self, experiment: Mapping[str, Any]) -> dict[str, Any]:
        normalized = normalize_experiment(experiment)
        now = _utc_now()
        with _LOCK:
            experiments = self._read()
            existing = next((
                item for item in experiments
                if item["experiment_id"] == normalized["experiment_id"]
            ), None)
            if existing:
                normalized["created_at"] = existing["created_at"]
                immutable_fields = (
                    "channel_id", "variable", "variants", "primary_metric",
                    "minimum_sample_size", "source_types",
                )
                definition_changed = any(
                    normalized[field] != existing[field]
                    for field in immutable_fields
                )
                if existing["status"] == RUNNING_STATUS and definition_changed:
                    raise ValueError("PAUSE_EXPERIMENT_BEFORE_EDITING_DEFINITION")
            normalized["updated_at"] = now
            if normalized["status"] == RUNNING_STATUS:
                conflicts = [
                    item["experiment_id"] for item in experiments
                    if item["experiment_id"] != normalized["experiment_id"]
                    and item["status"] == RUNNING_STATUS
                    and item["channel_id"].lower() == normalized["channel_id"].lower()
                ]
                if conflicts:
                    raise ValueError(
                        "CHANNEL_ALREADY_HAS_RUNNING_EXPERIMENT:" + ",".join(conflicts)
                    )
            experiments = [
                item for item in experiments
                if item["experiment_id"] != normalized["experiment_id"]
            ]
            experiments.append(normalized)
            experiments.sort(key=lambda item: item["experiment_id"])
            self._write(experiments)
        return deepcopy(normalized)

    def set_status(self, experiment_id: str, status: str) -> dict[str, Any]:
        experiment = self.get(experiment_id)
        if not experiment:
            raise ValueError("EXPERIMENT_NOT_FOUND")
        experiment["status"] = status
        return self.upsert(experiment)

    def delete(self, experiment_id: str) -> bool:
        target = str(experiment_id or "").strip()
        with _LOCK:
            experiments = self._read()
            remaining = [item for item in experiments if item["experiment_id"] != target]
            if len(remaining) == len(experiments):
                return False
            self._write(remaining)
        return True

    def active_for(
        self,
        channel_id: str,
        *,
        source_type: str = "",
        now: str = "",
    ) -> dict[str, Any] | None:
        target = _clean_channel_id(channel_id).lower()
        source = str(source_type or "").strip().lower()
        current = now or _utc_now()
        matches = []
        for experiment in self.list():
            if experiment["status"] != RUNNING_STATUS:
                continue
            if experiment["channel_id"].lower() != target:
                continue
            if experiment["source_types"] and source not in experiment["source_types"]:
                continue
            if _in_active_window(experiment, current):
                matches.append(experiment)
        if len(matches) > 1:
            raise ValueError("MULTIPLE_RUNNING_EXPERIMENTS_FOR_CHANNEL")
        return matches[0] if matches else None

    def assign(
        self,
        channel_id: str,
        content_key: str,
        *,
        source_type: str = "",
    ) -> dict[str, Any] | None:
        experiment = self.active_for(channel_id, source_type=source_type)
        return assign_experiment(experiment, content_key) if experiment else None


def resolve_experiment_assignment(
    channel_id: str,
    content_key: str,
    *,
    source_type: str = "",
    path: str = DEFAULT_EXPERIMENTS_PATH,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    if not _enabled(enabled, "CONTENT_EXPERIMENTS_ENABLED"):
        return None
    if not os.path.exists(path):
        return None
    return ExperimentManager(path).assign(
        channel_id,
        content_key,
        source_type=source_type,
    )


def evaluate_experiment(
    experiment: Mapping[str, Any],
    records: Iterable[Mapping[str, Any]],
    *,
    minimum_group_size: int = 5,
) -> dict[str, Any]:
    """Compare arms only inside story types represented in both variants."""
    normalized = normalize_experiment(experiment)
    variant_names = [item["name"] for item in normalized["variants"]]
    rows = latest_snapshots([
        dict(item) for item in records
        if str(item.get("experiment_id") or "") == normalized["experiment_id"]
        and _clean_channel_id(item.get("channel_id")).lower()
        == normalized["channel_id"].lower()
        and str(item.get("experiment_variant") or "") in variant_names
    ])
    minimum_group = max(1, int(minimum_group_size))
    story_groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        story_type = str(row.get("story_type") or "unknown")
        variant = str(row.get("experiment_variant") or "")
        story_groups.setdefault(story_type, {}).setdefault(variant, []).append(row)

    comparable_story_types = []
    comparable_rows = []
    group_reports = []
    for story_type, variants in sorted(story_groups.items()):
        eligible = all(len(variants.get(name, [])) >= minimum_group for name in variant_names)
        report = {
            "story_type": story_type,
            "eligible": eligible,
            "variants": {
                name: aggregate_performance(variants.get(name, []))
                for name in variant_names
            },
        }
        group_reports.append(report)
        if eligible:
            comparable_story_types.append(story_type)
            for name in variant_names:
                comparable_rows.extend(variants[name])

    summaries = {
        name: aggregate_performance([
            row for row in comparable_rows
            if row.get("experiment_variant") == name
        ])
        for name in variant_names
    }
    minimum_sample = normalized["minimum_sample_size"]
    eligible = bool(comparable_story_types) and all(
        summaries[name]["sample_size"] >= minimum_sample for name in variant_names
    )
    metric = normalized["primary_metric"]
    metric_values = {
        name: round(float(statistics.median([
            float(report["variants"][name].get(metric, 0) or 0)
            for report in group_reports
            if report["eligible"]
        ])), 3)
        if comparable_story_types else 0.0
        for name in variant_names
    }
    leader = ""
    uplift_percent = 0.0
    absolute_difference = 0.0
    if eligible and len(set(metric_values.values())) > 1:
        leader = (
            min(metric_values, key=metric_values.get)
            if metric in LOWER_IS_BETTER_METRICS
            else max(metric_values, key=metric_values.get)
        )
        other = next(name for name in variant_names if name != leader)
        absolute_difference = (
            metric_values[other] - metric_values[leader]
            if metric in LOWER_IS_BETTER_METRICS
            else metric_values[leader] - metric_values[other]
        )
        uplift_percent = (
            absolute_difference / abs(metric_values[other]) * 100.0
            if metric_values[other] else 0.0
        )
    return {
        "status": "ready_for_operator_review" if eligible else "insufficient_comparable_sample",
        "eligible": eligible,
        "experiment_id": normalized["experiment_id"],
        "channel_id": normalized["channel_id"],
        "variable": normalized["variable"],
        "primary_metric": metric,
        "minimum_sample_size_per_variant": minimum_sample,
        "minimum_group_size_per_variant": minimum_group,
        "comparable_story_types": comparable_story_types,
        "variants": summaries,
        "balanced_primary_metric": metric_values,
        "leader": leader,
        "winner": "",
        "operator_review_required": True,
        "absolute_difference": round(absolute_difference, 3),
        "uplift_percent": round(uplift_percent, 3),
        "story_type_comparisons": group_reports,
    }
