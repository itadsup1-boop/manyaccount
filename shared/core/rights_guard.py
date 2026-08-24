"""Basic rights policy for sources, media assets, and background music."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_POLICY_PATH = os.path.join(PROJECT_ROOT, "config", "media_source_policy.json")

_APPROVED = {"owned", "licensed", "permission", "public_domain", "remix_allowed"}
_BLOCKED = {"blocked", "denied", "do_not_use", "expired", "unlicensed"}


@dataclass(frozen=True)
class RightsReport:
    passed: bool
    status: str
    requires_review: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_rights_policy(path: str = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _status_from(*objects: Mapping[str, Any] | None) -> str:
    for obj in objects:
        if not obj:
            continue
        value = obj.get("rights_status") or obj.get("license_status")
        if value:
            return str(value).strip().lower()
    return "unknown"


def guard_source_rights(
    candidate: Mapping[str, Any] | None,
    source_config: Mapping[str, Any] | None = None,
    *,
    policy: Mapping[str, Any] | None = None,
) -> RightsReport:
    """Block explicit denials; flag unknown rights for operator review."""
    candidate = candidate or {}
    source_config = source_config or {}
    policy = dict(policy or load_rights_policy())
    approved = {str(item).lower() for item in policy.get("approved_statuses", _APPROVED)}
    blocked = {str(item).lower() for item in policy.get("blocked_statuses", _BLOCKED)}
    status = _status_from(candidate, source_config)
    errors: list[str] = []
    warnings: list[str] = []

    explicit_block = any(
        bool(obj.get(key))
        for obj in (candidate, source_config)
        for key in ("copyright_blocked", "do_not_use", "rights_denied")
    )
    if status in blocked or explicit_block:
        errors.append("Nguồn bị đánh dấu không có quyền sử dụng.")
    elif status in approved:
        pass
    else:
        warnings.append(
            "Chưa có hồ sơ quyền sử dụng cho nguồn; chỉ tiếp tục ở chế độ cảnh báo."
        )

    strict = str(policy.get("mode", "warn")).lower() == "strict"
    if strict and warnings:
        errors.append("Chế độ quyền nghiêm ngặt không cho phép nguồn chưa xác minh.")
    return RightsReport(
        passed=not errors,
        status=status,
        requires_review=bool(warnings),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def guard_music_rights(
    selection: Mapping[str, Any] | Any | None,
    *,
    policy: Mapping[str, Any] | None = None,
) -> RightsReport:
    """Only music explicitly marked approved may enter a production render."""
    policy = dict(policy or load_rights_policy())
    if selection is None:
        return RightsReport(True, "none", False, (), ())
    if isinstance(selection, Mapping):
        status = str(selection.get("license_status") or "unknown").lower()
        license_source = selection.get("license_source")
    else:
        status = str(getattr(selection, "license_status", "unknown")).lower()
        license_source = getattr(selection, "license_source", None)
    requires_approved = policy.get("music_requires_approved", True)
    passed = not requires_approved or (status == "approved" and bool(license_source))
    if passed:
        return RightsReport(True, status, False, (), ())
    return RightsReport(
        False,
        status,
        True,
        ("Nhạc nền chưa có trạng thái approved và nguồn giấy phép.",),
        (),
    )


def guard_media_assets(
    assets: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
) -> RightsReport:
    errors: list[str] = []
    warnings: list[str] = []
    statuses: list[str] = []
    for index, asset in enumerate(assets):
        report = guard_source_rights(asset, policy=policy)
        statuses.append(report.status)
        errors.extend(f"Asset #{index + 1}: {message}" for message in report.errors)
        warnings.extend(f"Asset #{index + 1}: {message}" for message in report.warnings)
    return RightsReport(
        passed=not errors,
        status=",".join(statuses) or "none",
        requires_review=bool(warnings),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
