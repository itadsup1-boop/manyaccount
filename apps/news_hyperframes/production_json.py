"""Strict, dependency-free validation for News Video Production JSON v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re


class ProductionJsonError(ValueError):
    """A JSON production plan is incomplete or unsafe to render."""


ALLOWED_RIGHTS_MODES = {
    "facts_and_licensed_real_stock_only",
    "facts_and_original_graphics_only",
}
ALLOWED_MEDIA_LICENSES = {"licensed_real_stock", "owned_original"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _required_string(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ProductionJsonError(f"Thiếu trường bắt buộc: {field}.")
    return result


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProductionJsonError(f"{field} phải là số.") from exc


@dataclass(frozen=True)
class Beat:
    beat_id: str
    start_sec: float
    end_sec: float
    voice_over: str
    on_screen_text: str
    visual_fallback: str
    asset_ids: tuple[str, ...]

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


@dataclass(frozen=True)
class ProductionPlan:
    raw: dict[str, Any]
    duration_sec: float
    voice_over: str
    title: str
    rights_mode: str
    beats: tuple[Beat, ...]

    @classmethod
    def from_path(cls, path: str | Path) -> "ProductionPlan":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProductionJsonError("File JSON không hợp lệ.") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductionPlan":
        if not isinstance(data, dict):
            raise ProductionJsonError("JSON gốc phải là một object.")
        if int(data.get("schema_version") or 0) != 2:
            raise ProductionJsonError("Chỉ nhận News Video Production JSON v2.")
        if data.get("input_status") != "ready" or data.get("should_make_video") is not True:
            raise ProductionJsonError("JSON chưa sẵn sàng để dựng video.")

        target = data.get("target") or {}
        render_spec = data.get("render_spec") or {}
        duration = _number(target.get("duration_sec"), "target.duration_sec")
        if duration < 20 or duration > 120:
            raise ProductionJsonError("Thời lượng JSON phải nằm trong khoảng 20–120 giây.")
        if render_spec.get("width") != 1080 or render_spec.get("height") != 1920:
            raise ProductionJsonError("Video bắt buộc là 1080x1920.")
        if int(render_spec.get("fps") or 0) != 30:
            raise ProductionJsonError("Video bắt buộc là 30 fps.")

        policy = data.get("rights_policy") or {}
        mode = _required_string(policy.get("mode"), "rights_policy.mode")
        if mode not in ALLOWED_RIGHTS_MODES:
            raise ProductionJsonError("Chế độ quyền sử dụng không được renderer này chấp nhận.")
        if policy.get("publisher_assets_allowed") is True or policy.get("logos_allowed") is True:
            raise ProductionJsonError("JSON không được cho phép asset toà soạn hoặc logo.")

        source = data.get("source") or {}
        source_url = _required_string(source.get("url"), "source.url")
        if not re.fullmatch(r"https?://[^\s\[\]()]+", source_url):
            raise ProductionJsonError(
                "source.url phải là URL thuần bắt đầu bằng http(s), không phải Markdown link."
            )

        raw_beats = data.get("beats")
        if not isinstance(raw_beats, list) or not 7 <= len(raw_beats) <= 9:
            raise ProductionJsonError("JSON cần có từ 7 đến 9 beats.")
        beats: list[Beat] = []
        previous_end = 0.0
        for index, item in enumerate(raw_beats, start=1):
            if not isinstance(item, dict):
                raise ProductionJsonError(f"beats[{index}] phải là object.")
            start = _number(item.get("start_sec"), f"beats[{index}].start_sec")
            end = _number(item.get("end_sec"), f"beats[{index}].end_sec")
            if start < previous_end - 0.12 or end <= start:
                raise ProductionJsonError(f"Mốc thời gian beats[{index}] bị chồng chéo hoặc ngược.")
            if end - start < 2.0:
                raise ProductionJsonError(f"beats[{index}] quá ngắn để đọc phụ đề.")
            asset_ids = item.get("asset_ids") or []
            if not isinstance(asset_ids, list) or not all(isinstance(asset, str) for asset in asset_ids):
                raise ProductionJsonError(f"beats[{index}].asset_ids phải là mảng chuỗi.")
            beats.append(
                Beat(
                    beat_id=str(item.get("beat_id") or f"beat_{index}"),
                    start_sec=start,
                    end_sec=end,
                    voice_over=_required_string(item.get("voice_over"), f"beats[{index}].voice_over"),
                    on_screen_text=_required_string(item.get("on_screen_text"), f"beats[{index}].on_screen_text"),
                    visual_fallback=_required_string(item.get("visual_fallback"), f"beats[{index}].visual_fallback"),
                    asset_ids=tuple(asset_ids),
                )
            )
            previous_end = end
        if abs(beats[-1].end_sec - duration) > 1.0:
            raise ProductionJsonError("Beat cuối phải kết thúc gần bằng target.duration_sec.")

        voice = str(data.get("full_voice_over") or data.get("script_voice") or "").strip()
        if not voice:
            voice = " ".join(beat.voice_over for beat in beats)
        title = str(data.get("title_tiktok") or data.get("main_idea") or beats[0].on_screen_text).strip()
        return cls(data, duration, voice, title, mode, tuple(beats))


def approved_local_assets(plan: ProductionPlan, media_root: str | Path | None = None) -> dict[str, Path]:
    """Return only usable local real-stock/owned assets declared by the JSON."""
    root = Path(media_root).resolve() if media_root else None
    selected: dict[str, Path] = {}
    for item in plan.raw.get("assets") or []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "").strip()
        if not asset_id or str(item.get("license_status") or "").strip() not in ALLOWED_MEDIA_LICENSES:
            continue
        if item.get("is_ai_generated") is True or item.get("publisher_asset") is True:
            continue
        raw_path = str(item.get("local_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if root and root not in path.parents and path != root:
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS or not path.is_file():
            continue
        selected[asset_id] = path
    return selected


def filename_safe(value: str, fallback: str = "news-video") -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return clean[:48] or fallback
