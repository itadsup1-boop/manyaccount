"""Validate text/logo placement against platform UI reserved regions."""

from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Mapping


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAFE_ZONE_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "video_safe_zones.json")


@dataclass(frozen=True)
class SafeZoneResult:
    passed: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TextLayout:
    lines: tuple[str, ...]
    x: int
    y: int
    width: int
    height: int
    line_spacing: int

    def to_box(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@lru_cache(maxsize=1)
def load_safe_zones() -> dict[str, Any]:
    try:
        with open(SAFE_ZONE_CONFIG_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_safe_zone(platform: str = "") -> dict[str, Any]:
    payload = load_safe_zones()
    platform_key = str(platform or payload.get("default_platform") or "tiktok_9_16")
    platforms = payload.get("platforms", {})
    zone = platforms.get(platform_key, {}) if isinstance(platforms, Mapping) else {}
    return dict(zone) if isinstance(zone, Mapping) else {}


def get_subtitle_constraints(platform: str = "", long_caption: bool = False) -> dict[str, Any]:
    zone = get_safe_zone(platform)
    key = "subtitle_long" if long_caption else "subtitle"
    constraints = zone.get(key, {})
    return dict(constraints) if isinstance(constraints, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def plan_text_layout(
    text: str,
    *,
    font_size: int,
    kind: str = "hook",
    preferred_x: int | None = None,
    preferred_y: int | None = None,
    max_width: int | None = None,
    platform: str = "",
) -> TextLayout:
    """Wrap and clamp a text box inside the configured platform safe zone."""
    zone = get_safe_zone(platform)
    allowed = zone.get(kind) or zone.get("content_safe") or {}
    left = int(_number(allowed.get("left"), 60))
    top = int(_number(allowed.get("top"), 150))
    right = int(_number(allowed.get("right"), 900))
    bottom = int(_number(allowed.get("bottom"), 1500))
    width = min(int(max_width or right - left), right - left)
    width = max(1, width)
    max_lines = int(allowed.get("max_lines", 2) or 2)
    max_chars = max(1, int(width / max(1.0, int(font_size) * 0.55)))
    lines = tuple(textwrap.wrap(str(text or "").strip(), width=max_chars))
    if len(lines) > max_lines:
        raise ValueError(
            f"SAFE_ZONE_TOO_MANY_LINES: {len(lines)} > {max_lines}"
        )

    line_spacing = max(int(font_size), int(round(font_size * 1.2)))
    height = line_spacing * max(1, len(lines))
    wanted_x = (left + right - width) // 2 if preferred_x is None else int(preferred_x)
    wanted_y = top if preferred_y is None else int(preferred_y)
    x = max(left, min(wanted_x, right - width))
    y = max(top, min(wanted_y, bottom - height))
    layout = TextLayout(lines, x, y, width, height, line_spacing)
    result = validate_element_box(
        kind,
        layout.to_box(),
        platform=platform,
        line_count=max(1, len(lines)),
    )
    if not result.passed:
        raise ValueError("; ".join(result.errors))
    return layout


def validate_element_box(
    kind: str,
    box: Mapping[str, Any],
    *,
    platform: str = "",
    line_count: int = 1,
) -> SafeZoneResult:
    zone = get_safe_zone(platform)
    allowed = zone.get(kind) or zone.get("content_safe") or {}
    x = _number(box.get("x"))
    y = _number(box.get("y"))
    width = max(0.0, _number(box.get("width")))
    height = max(0.0, _number(box.get("height")))
    right = x + width
    bottom = y + height
    errors: list[str] = []
    warnings: list[str] = []

    if width <= 0 or height <= 0:
        errors.append("SAFE_ZONE_INVALID_BOX")
    if x < _number(allowed.get("left")) or y < _number(allowed.get("top")):
        errors.append(f"SAFE_ZONE_{kind.upper()}_TOP_LEFT")
    if right > _number(allowed.get("right"), 1080) or bottom > _number(allowed.get("bottom"), 1920):
        errors.append(f"SAFE_ZONE_{kind.upper()}_BOTTOM_RIGHT")
    max_lines = int(allowed.get("max_lines", 2) or 2)
    if line_count > max_lines:
        errors.append("SAFE_ZONE_TOO_MANY_LINES")
    if right > _number(zone.get("content_safe", {}).get("right"), 900) - 30:
        warnings.append("SAFE_ZONE_NEAR_RIGHT_CONTROLS")
    return SafeZoneResult(not errors, tuple(dict.fromkeys(errors)), tuple(dict.fromkeys(warnings)))


def validate_subtitle_layout(
    *,
    font_size: int,
    margin_v: int,
    margin_l: int,
    margin_r: int,
    max_lines: int = 2,
    platform: str = "",
) -> SafeZoneResult:
    rules = get_subtitle_constraints(platform)
    errors: list[str] = []
    warnings: list[str] = []
    if font_size < int(rules.get("min_font_size", 46)):
        warnings.append("SUBTITLE_FONT_TOO_SMALL")
    if font_size > int(rules.get("max_font_size", 76)):
        errors.append("SUBTITLE_FONT_TOO_LARGE")
    if margin_v < int(rules.get("min_margin_bottom", 320)):
        errors.append("SUBTITLE_OVER_BOTTOM_CAPTION")
    if margin_v > int(rules.get("max_margin_bottom", 760)):
        warnings.append("SUBTITLE_TOO_HIGH")
    if margin_l < int(rules.get("min_margin_left", 40)):
        errors.append("SUBTITLE_TOO_CLOSE_LEFT_EDGE")
    if margin_r < int(rules.get("min_margin_right", 100)):
        errors.append("SUBTITLE_UNDER_RIGHT_CONTROLS")
    if max_lines > int(rules.get("max_lines", 2)):
        errors.append("SUBTITLE_TOO_MANY_LINES")
    return SafeZoneResult(not errors, tuple(errors), tuple(warnings))


def validate_ass_file(path: str, platform: str = "") -> SafeZoneResult:
    if not path or not os.path.exists(path):
        return SafeZoneResult(True, (), ("SUBTITLE_LAYOUT_METADATA_MISSING",))
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except OSError:
        return SafeZoneResult(False, ("SUBTITLE_ASS_UNREADABLE",), ())

    style_match = re.search(r"^Style:\s*Default,([^\n]+)$", text, re.MULTILINE)
    if not style_match:
        return SafeZoneResult(False, ("SUBTITLE_ASS_STYLE_MISSING",), ())
    fields = [value.strip() for value in style_match.group(1).split(",")]
    if len(fields) < 22:
        return SafeZoneResult(False, ("SUBTITLE_ASS_STYLE_INVALID",), ())
    layout = validate_subtitle_layout(
        font_size=int(float(fields[1])),
        margin_l=int(float(fields[18])),
        margin_r=int(float(fields[19])),
        margin_v=int(float(fields[20])),
        platform=platform,
    )
    dialogue = [line for line in text.splitlines() if line.startswith("Dialogue:")]
    if any(line.count(r"\N") > 1 for line in dialogue):
        return SafeZoneResult(
            False,
            tuple((*layout.errors, "SUBTITLE_TOO_MANY_LINES")),
            layout.warnings,
        )
    return layout
