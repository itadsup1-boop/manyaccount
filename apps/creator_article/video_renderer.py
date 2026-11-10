"""Renderer preview cho kịch bản khoá — B-roll thật + graphic fallback.

Theo ``BRIEF_AGENT_DUNG_VIDEO_TIN_TUC.md`` §6/§7:

- Mỗi beat là một segment MP4 1080x1920, 30 fps, H.264 rồi nối bằng concat
  (transition mặc định là ``cut``; ``fade`` => fade-in đầu segment).
- B-roll: clip video cover-crop 9:16; ảnh tĩnh chỉ pan/zoom nhẹ (Ken Burns).
- ``DATA GRAPHIC:``/``MAP GRAPHIC:``/beat thiếu asset => card tự dựng bằng PIL,
  không nhái bản đồ thương mại, không logo.
- Chữ trên hình nằm trong content safe area của ``config/video_safe_zones.json``
  (nguồn chuẩn của dự án; thiếu file thì rơi về 72/180/1560 theo BRIEF §7).

Preview Giai đoạn 3 render KHÔNG voice; voice + phụ đề + BGM do
``final_video.py`` (Giai đoạn 4) dựng thành final.mp4 hoàn chỉnh.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Mapping

from adsup_central_hub.backend.production_jobs import (
    JOBS_DIR,
    load_job_artifact,
)
from apps.creator_article.media_planner import (
    GRAPHIC_KINDS,
    KIND_BROLL,
    KIND_DATA_GRAPHIC,
    KIND_FACT_CARD,
    KIND_MAP_GRAPHIC,
    KIND_NO_ASSET,
    KIND_QUOTE_CARD,
    classify_visual_query,
)
from shared.core.rights_guard import guard_media_assets

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30
FADE_DURATION = 0.35
MIN_SEGMENT_SECONDS = 0.5

FONT_PATH = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")

SAFE_ZONE_PATH = os.path.join(PROJECT_ROOT, "config", "video_safe_zones.json")
SAFE_ZONE_FALLBACK = {"left": 72, "top": 180, "right": 1008, "bottom": 1560}

# Nền card navy phải có luma > ngưỡng blackdetect của VideoQA (0.10*255 ≈ 25.5):
# (13,20,38) luma ~20 bị chấm là khung đen giả; (24,36,64) luma ~35.6, vẫn navy đậm.
COLOR_BG = (24, 36, 64)
COLOR_GRID = (44, 58, 92)
COLOR_TEXT = (255, 255, 255)
COLOR_SECONDARY = (148, 163, 184)
COLOR_ACCENT = (245, 197, 66)
COLOR_PIN = (239, 68, 68)

from shared.core.video_encoding import CLEAN_METADATA_ARGS, FINAL_VIDEO_ARGS


def load_content_safe_zone(path: str = SAFE_ZONE_PATH) -> dict[str, int]:
    """Content safe area 9:16 — ưu tiên config dự án, fallback BRIEF §7."""

    try:
        import json

        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        box = (
            data.get("platforms", {})
            .get(data.get("default_platform", "tiktok_9_16"), {})
            .get("content_safe")
        )
        if isinstance(box, Mapping) and all(
            isinstance(box.get(key), (int, float)) for key in ("left", "top", "right", "bottom")
        ):
            return {key: int(box[key]) for key in ("left", "top", "right", "bottom")}
    except (OSError, ValueError):
        pass
    return dict(SAFE_ZONE_FALLBACK)


# ═══════════════════════ PIL: wrap chữ + card đồ hoạ ═══════════════════════


def _load_font(size: int):
    from PIL import ImageFont

    return ImageFont.truetype(FONT_PATH, size)


def wrap_text(text: str, font: Any, max_width: int, max_lines: int = 2) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines]


def _fit_font(text: str, *, max_width: int, start_size: int, min_size: int, max_lines: int) -> tuple[Any, list[str]]:
    size = start_size
    while size >= min_size:
        font = _load_font(size)
        lines = wrap_text(text, font, max_width, max_lines=max_lines)
        if len(lines) < max_lines or all(font.getlength(line) <= max_width for line in lines):
            return font, lines
        size -= 6
    font = _load_font(min_size)
    return font, wrap_text(text, font, max_width, max_lines=max_lines)


def _draw_centered(
    draw: Any,
    lines: list[str],
    font: Any,
    *,
    y: int,
    fill: Any,
    stroke: int = 0,
    center_x: float = CANVAS_W / 2,
) -> int:
    for line in lines:
        width = font.getlength(line)
        draw.text(
            (center_x - width / 2, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke,
            stroke_fill=(0, 0, 0),
        )
        y += int(font.size * 1.25)
    return y


def _center_x(safe: Mapping[str, int]) -> float:
    return (int(safe["left"]) + int(safe["right"])) / 2


def _headline_y(safe: Mapping[str, int]) -> int:
    return int(safe["top"]) + 20


def _max_text_width(safe: Mapping[str, int]) -> int:
    return int(safe["right"]) - int(safe["left"])


_META_INSTRUCTION_MARKERS = (
    "đồ họa",
    "đồ hoạ",
    "tự dựng",
    "nguyên gốc",
    "không dùng",
    "thẻ so sánh",
    "sơ đồ",
    "minh họa",
    "minh hoạ",
    "typography",
    "vector",
    "biểu tượng",
    "nền xanh",
)


def _clean_card_caption(text: str) -> str:
    """Loại bỏ chỉ dẫn dựng hình nội bộ (visual_fallback) khỏi chữ hiện trên card."""
    cleaned = str(text or "").strip()
    if not cleaned or len(cleaned) > 65:
        return ""
    lowered = cleaned.lower()
    if any(marker in lowered for marker in _META_INSTRUCTION_MARKERS):
        return ""
    return cleaned


def build_data_graphic_card(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """BRIEF §7: một thông điệp, tối đa 2 số liên quan, số lớn + nhãn ngắn."""

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)
    draw = ImageDraw.Draw(image)

    headline = str(beat.get("on_screen_text") or "")
    must_show = [str(item) for item in (beat.get("must_show") or []) if str(item).strip()]
    caption = _clean_card_caption(classify_visual_query(str(beat.get("visual_query") or ""))[1])

    width = _max_text_width(safe)
    center = _center_x(safe)
    font_h, lines_h = _fit_font(headline, max_width=width, start_size=76, min_size=48, max_lines=2)
    y = _draw_centered(draw, lines_h, font_h, y=_headline_y(safe), fill=COLOR_TEXT, stroke=2, center_x=center)

    if must_show:
        y = int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.38)
        draw.rectangle(
            [center - 70, y - 26, center + 70, y - 18],
            fill=COLOR_ACCENT,
        )
        font_big, lines_big = _fit_font(must_show[0], max_width=width, start_size=180, min_size=96, max_lines=2)
        y = _draw_centered(draw, lines_big, font_big, y=y, fill=COLOR_ACCENT, stroke=0, center_x=center)
        if len(must_show) > 1:
            font_sub, lines_sub = _fit_font(must_show[1], max_width=width, start_size=92, min_size=56, max_lines=2)
            _draw_centered(draw, lines_sub, font_sub, y=y + 60, fill=COLOR_TEXT, stroke=2, center_x=center)

    if caption:
        font_c = _load_font(42)
        lines_c = wrap_text(caption, font_c, width, max_lines=2)
        _draw_centered(draw, lines_c, font_c, y=int(safe["bottom"]) - 150, fill=COLOR_SECONDARY, center_x=center)
    return image


def build_map_graphic_card(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """BRIEF §7: sơ đồ tối giản — lưới, marker, tên địa danh; không nhái bản đồ thương mại."""

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)
    draw = ImageDraw.Draw(image)
    for x in range(0, CANVAS_W + 1, 120):
        draw.line([(x, 0), (x, CANVAS_H)], fill=COLOR_GRID, width=2)
    for y in range(0, CANVAS_H + 1, 120):
        draw.line([(0, y), (CANVAS_W, y)], fill=COLOR_GRID, width=2)

    headline = str(beat.get("on_screen_text") or "")
    must_show = [str(item) for item in (beat.get("must_show") or []) if str(item).strip()]
    place = must_show[0] if must_show else classify_visual_query(str(beat.get("visual_query") or ""))[1]

    width = _max_text_width(safe)
    center = _center_x(safe)
    font_h, lines_h = _fit_font(headline, max_width=width, start_size=76, min_size=48, max_lines=2)
    _draw_centered(draw, lines_h, font_h, y=_headline_y(safe), fill=COLOR_TEXT, stroke=2, center_x=center)

    pin_x, pin_y = CANVAS_W // 2, int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.5)
    radius = 34
    draw.ellipse(
        [pin_x - radius, pin_y - radius - 60, pin_x + radius, pin_y + radius - 60],
        fill=COLOR_PIN,
        outline=COLOR_TEXT,
        width=4,
    )
    draw.polygon([(pin_x - 18, pin_y - 70), (pin_x + 18, pin_y - 70), (pin_x, pin_y - 24)], fill=COLOR_PIN)
    draw.ellipse([pin_x - 10, pin_y - 80, pin_x + 10, pin_y - 60], fill=COLOR_TEXT)

    if place:
        label = place if len(place) <= 42 else place[:39] + "..."
        font_l, _ = _fit_font(label, max_width=width - 80, start_size=64, min_size=40, max_lines=1)
        label_w = font_l.getlength(label)
        box_w, box_h = int(label_w) + 60, 96
        draw.rounded_rectangle(
            [pin_x - box_w / 2, pin_y + 10, pin_x + box_w / 2, pin_y + 10 + box_h],
            radius=20,
            fill=(30, 41, 66),
            outline=COLOR_ACCENT,
            width=3,
        )
        draw.text((pin_x - label_w / 2, pin_y + 10 + 18), label, font=font_l, fill=COLOR_TEXT)

    font_c = _load_font(40)
    caption_map = "Sơ đồ minh hoạ - không theo tỷ lệ thực"
    draw.text(
        (center - font_c.getlength(caption_map) / 2, int(safe["bottom"]) - 120),
        caption_map,
        font=font_c,
        fill=COLOR_SECONDARY,
    )
    return image


def build_typography_card(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """Fallback khi không có B-roll trung thực — không ép asset yếu vào cảnh."""

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)
    draw = ImageDraw.Draw(image)
    width = _max_text_width(safe)

    headline = str(beat.get("on_screen_text") or "")
    if not headline:
        headline = classify_visual_query(str(beat.get("visual_query") or ""))[1] or "Dữ kiện"
    center = _center_x(safe)
    draw.rectangle([center - 90, int(CANVAS_H * 0.36), center + 90, int(CANVAS_H * 0.36) + 10], fill=COLOR_ACCENT)

    font_h, lines_h = _fit_font(headline, max_width=width, start_size=96, min_size=56, max_lines=3)
    _draw_centered(draw, lines_h, font_h, y=int(CANVAS_H * 0.40), fill=COLOR_TEXT, stroke=3, center_x=center)

    must_show = [str(item) for item in (beat.get("must_show") or []) if str(item).strip()]
    if must_show:
        font_s, lines_s = _fit_font(must_show[0], max_width=width, start_size=72, min_size=44, max_lines=2)
        _draw_centered(draw, lines_s, font_s, y=int(CANVAS_H * 0.62), fill=COLOR_ACCENT, stroke=2, center_x=center)
    return image


def build_quote_card(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """BRIEF §6/§7: Quote Card cho trích dẫn phát ngôn trong safe zone."""

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)
    draw = ImageDraw.Draw(image)
    width = _max_text_width(safe)
    center = _center_x(safe)

    headline = str(beat.get("on_screen_text") or "TRÍCH DẪN")
    must_show = [str(item) for item in (beat.get("must_show") or []) if str(item).strip()]
    cleaned_query = _clean_card_caption(classify_visual_query(str(beat.get("visual_query") or ""))[1])
    quote_body = must_show[0] if must_show else (cleaned_query or headline)
    attribution = must_show[1] if len(must_show) > 1 else (cleaned_query if must_show else "")

    font_h, lines_h = _fit_font(headline, max_width=width, start_size=68, min_size=44, max_lines=2)
    _draw_centered(draw, lines_h, font_h, y=_headline_y(safe), fill=COLOR_ACCENT, stroke=2, center_x=center)

    box_top = int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.25)
    box_bottom = int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.72)
    draw.rounded_rectangle(
        [int(safe["left"]) + 16, box_top, int(safe["right"]) - 16, box_bottom],
        radius=28,
        fill=(32, 48, 82),
        outline=COLOR_ACCENT,
        width=4,
    )

    font_q, lines_q = _fit_font(
        f'“{quote_body}”', max_width=width - 80, start_size=76, min_size=44, max_lines=4
    )
    y_after = _draw_centered(
        draw, lines_q, font_q, y=box_top + 60, fill=COLOR_TEXT, stroke=2, center_x=center
    )
    if attribution:
        font_a, lines_a = _fit_font(
            f"— {attribution}", max_width=width - 80, start_size=48, min_size=36, max_lines=2
        )
        _draw_centered(
            draw, lines_a, font_a, y=min(y_after + 32, box_bottom - 90), fill=COLOR_SECONDARY, center_x=center
        )
    return image


def build_fact_card(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """BRIEF §6/§7: Fact Card nhấn mạnh dữ kiện/mốc sự kiện trong safe zone."""

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)
    draw = ImageDraw.Draw(image)
    width = _max_text_width(safe)
    center = _center_x(safe)

    headline = str(beat.get("on_screen_text") or "DỮ KIỆN CHÍNH")
    must_show = [str(item) for item in (beat.get("must_show") or []) if str(item).strip()]
    cleaned_query = _clean_card_caption(classify_visual_query(str(beat.get("visual_query") or ""))[1])

    font_h, lines_h = _fit_font(headline, max_width=width, start_size=76, min_size=48, max_lines=2)
    _draw_centered(draw, lines_h, font_h, y=_headline_y(safe), fill=COLOR_TEXT, stroke=2, center_x=center)

    box_top = int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.28)
    box_bottom = int(safe["top"] + (safe["bottom"] - safe["top"]) * 0.72)
    draw.rounded_rectangle(
        [int(safe["left"]) + 16, box_top, int(safe["right"]) - 16, box_bottom],
        radius=24,
        fill=(30, 44, 76),
        outline=COLOR_ACCENT,
        width=3,
    )

    primary = must_show[0] if must_show else (cleaned_query or headline)
    font_p, lines_p = _fit_font(primary, max_width=width - 80, start_size=88, min_size=48, max_lines=3)
    y_next = _draw_centered(
        draw, lines_p, font_p, y=box_top + 60, fill=COLOR_ACCENT, stroke=2, center_x=center
    )
    secondary = must_show[1] if len(must_show) > 1 else (cleaned_query if must_show else "")
    if secondary:
        font_s, lines_s = _fit_font(secondary, max_width=width - 80, start_size=56, min_size=40, max_lines=2)
        _draw_centered(
            draw, lines_s, font_s, y=min(y_next + 36, box_bottom - 100), fill=COLOR_TEXT, stroke=1, center_x=center
        )
    return image


def build_text_overlay(beat: Mapping[str, Any], safe: Mapping[str, int]) -> Any:
    """Overlay RGBA cho B-roll: headline nằm trong content safe area."""

    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    headline = str(beat.get("on_screen_text") or "")
    if not headline:
        return overlay
    width = _max_text_width(safe)
    font_h, lines_h = _fit_font(headline, max_width=width, start_size=72, min_size=44, max_lines=2)
    _draw_centered(
        draw, lines_h, font_h, y=_headline_y(safe), fill=COLOR_TEXT + (255,), stroke=3, center_x=_center_x(safe)
    )
    return overlay


# ═══════════════════════ Kế hoạch render (thuần, test được) ═══════════════════════


_STRICT_MEDIA_POLICY = {"mode": "strict"}


def _asset_reject_reason(entry: Mapping[str, Any]) -> str:
    """Lý do loại asset theo KE_HOACH §8; rỗng nghĩa là dùng được.

    Thứ tự: provenance/license (rights_guard strict) -> watermark phát hiện ->
    quét lỗi/chưa chạy. Asset chưa quét bị coi là chưa xác minh (bị loại).
    """

    report = guard_media_assets([entry], policy=_STRICT_MEDIA_POLICY)
    if not report.passed:
        return "rights_guard_failed"
    logo_scan = str(entry.get("logo_scan") or "")
    wm_scan = entry.get("watermark_scan")
    if wm_scan == "detected" or (isinstance(wm_scan, Mapping) and wm_scan.get("detected")):
        return "watermark_detected"
    if isinstance(wm_scan, Mapping) and wm_scan.get("error"):
        return "watermark_scan_error"
    if logo_scan in ("pending", "", "error"):
        return "watermark_scan_missing"
    return ""


def _segment_duration(beat: Mapping[str, Any]) -> float:
    start = float(beat.get("start_sec") or 0)
    end = float(beat.get("end_sec") or 0)
    duration = end - start if end > start else float(beat.get("duration_hint") or 0)
    return max(MIN_SEGMENT_SECONDS, round(duration, 3))


def _motion_for(beat: Mapping[str, Any], is_still: bool) -> str:
    motion = str(beat.get("motion") or "").strip()
    if motion in {"static", "slow_push_in", "slow_pull_out", "pan_left", "pan_right"}:
        return motion
    return "slow_push_in" if is_still else "static"


def build_render_plan(
    storyboard: Mapping[str, Any],
    media_plan: Mapping[str, Any],
    manifest: list[Mapping[str, Any]],
    *,
    job_dir: str,
    safe: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Ghép storyboard + media plan + manifest thành danh sách segment cụ thể.

    Gate KE_HOACH §8: beat broll trỏ asset_id không có bản ghi manifest -> chặn
    (``PROVENANCE_MISSING``); bản ghi thiếu provenance/license hoặc quét
    watermark phát hiện/chưa chạy -> loại asset, rơi về graphic fallback.
    """

    safe = safe or load_content_safe_zone()
    assets_by_id = {str(entry.get("asset_id")): entry for entry in manifest if entry.get("asset_id")}
    plan_by_beat = {
        entry.get("beat_number"): entry
        for entry in media_plan.get("beats", [])
        if isinstance(entry, Mapping)
    }
    segments: list[dict[str, Any]] = []
    warnings: list[str] = []
    for beat in storyboard.get("beats", []):
        if not isinstance(beat, Mapping):
            continue
        beat_number = beat.get("beat_number")
        plan = plan_by_beat.get(beat_number) or {}
        kind = str(plan.get("kind") or KIND_NO_ASSET)
        asset_id = plan.get("asset_id")
        visual: dict[str, Any] = {"type": "card", "path": "", "motion": "slow_push_in"}

        if kind == KIND_BROLL and asset_id:
            entry = assets_by_id.get(str(asset_id))
            if entry is None:
                raise ValueError(
                    f"PROVENANCE_MISSING: beat {beat_number} trỏ asset {asset_id} nhưng "
                    "assets_manifest.json không có bản ghi — chạy lại 'Tìm tư liệu'."
                )
            reject = _asset_reject_reason(entry)
            local_rel = str(entry.get("local_path") or "")
            local_path = os.path.join(job_dir, local_rel) if local_rel else ""
            if reject:
                warnings.append(
                    f"Beat {beat_number}: asset {asset_id} bị loại ({reject}) theo KE_HOACH §8 -> graphic fallback"
                )
                kind = KIND_NO_ASSET
            elif local_path and os.path.isfile(local_path):
                media_type = str(entry.get("media_type") or "video")
                visual = {
                    "type": "video" if media_type == "video" else "photo",
                    "path": local_path,
                    "motion": _motion_for(beat, is_still=media_type != "video"),
                }
            else:
                warnings.append(f"Beat {beat_number}: asset {asset_id} không có file local -> typography fallback")
                kind = KIND_NO_ASSET
        elif kind == KIND_BROLL and not asset_id:
            kind = KIND_NO_ASSET

        if kind in GRAPHIC_KINDS:
            visual = {"type": "card", "path": "graphics", "motion": _motion_for(beat, is_still=True)}
        elif kind == KIND_NO_ASSET:
            visual = {"type": "card", "path": "graphics", "motion": "slow_push_in"}

        segments.append(
            {
                "beat_number": beat_number,
                "kind": kind if kind != KIND_BROLL else KIND_BROLL,
                "visual": visual,
                "duration": _segment_duration(beat),
                "start_sec": float(beat.get("start_sec") or 0),
                "transition": str(beat.get("transition") or "cut"),
                # Các hàm build_*_card/build_text_overlay đọc theo key kiểu beat.
                "on_screen_text": str(beat.get("on_screen_text") or ""),
                "must_show": [str(item) for item in (beat.get("must_show") or [])],
                "visual_query": str(beat.get("visual_query") or ""),
                "asset_id": asset_id if kind == KIND_BROLL else None,
            }
        )
    return {"segments": segments, "warnings": warnings}


# ═══════════════════════ FFmpeg: render từng segment + concat ═══════════════════════


def render_segment_files(
    segments: list[Mapping[str, Any]],
    *,
    render_dir: str,
    safe: Mapping[str, int],
) -> list[str]:
    """Render tuần tự từng beat thành seg_XXX.mp4; trả về danh sách đường dẫn."""

    paths: list[str] = []
    for index, segment in enumerate(segments):
        paths.append(_render_segment(segment, index=index, render_dir=render_dir, safe=safe))
    return paths


def concat_segments(seg_paths: list[str], output_path: str, *, list_path: str) -> None:
    """Nối các segment (đã cùng chuẩn encode) bằng concat demuxer, -c copy."""

    with open(list_path, "w", encoding="utf-8") as handle:
        for path in seg_paths:
            handle.write(f"file '{path}'\n")
    args = ["-f", "concat", "-safe", "0", "-i", list_path]
    args += ["-map", "0:v", "-c", "copy", "-movflags", "+faststart", *CLEAN_METADATA_ARGS, output_path]
    _run_ffmpeg(args, what="nối segment thành video")


def _run_ffmpeg(args: list[str], *, what: str) -> None:
    binary = os.getenv("FFMPEG_BINARY", "ffmpeg")
    result = subprocess.run(
        [binary, "-y", *args], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"FFmpeg lỗi khi {what}: {tail}")


def _still_chain(motion: str, num_frames: int) -> str:
    if motion == "slow_pull_out":
        scale = f"scale=w='1242-108*n/{num_frames}':h='2208-192*n/{num_frames}':eval=frame"
    elif motion == "static":
        scale = "scale=1134:2016"
    else:
        scale = f"scale=w='1134+108*n/{num_frames}':h='2016+192*n/{num_frames}':eval=frame"
    return f"{scale},crop=1080:1920:x='(iw-1080)/2':y='(ih-1920)/2',setsar=1,fps=30"


def _render_segment(
    segment: Mapping[str, Any],
    *,
    index: int,
    render_dir: str,
    safe: Mapping[str, int],
) -> str:
    """Render một segment (kèm overlay chữ cho B-roll). Trả về đường dẫn mp4."""

    from PIL import Image

    out_path = os.path.join(render_dir, f"seg_{index:03d}.mp4")
    duration = float(segment["duration"])
    visual = segment["visual"]
    fade_in = segment.get("transition") == "fade"
    fade_filter = f",fade=t=in:st=0:d={FADE_DURATION}" if fade_in else ""

    args: list[str] = []
    if visual["type"] == "video":
        args += ["-ss", "0", "-t", f"{duration:.3f}", "-i", visual["path"]]
        video_chain = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30{fade_filter}[vbase]"
        )
    else:
        if visual["type"] == "photo":
            source = visual["path"]
        else:
            source = os.path.join(render_dir, f"card_{index:03d}.png")
            card = (
                build_data_graphic_card(segment, safe)
                if segment["kind"] == KIND_DATA_GRAPHIC
                else build_map_graphic_card(segment, safe)
                if segment["kind"] == KIND_MAP_GRAPHIC
                else build_quote_card(segment, safe)
                if segment["kind"] == KIND_QUOTE_CARD
                else build_fact_card(segment, safe)
                if segment["kind"] == KIND_FACT_CARD
                else build_typography_card(segment, safe)
            )
            card.save(source)
        args += ["-loop", "1", "-t", f"{duration:.3f}", "-i", source]
        num_frames = max(1, int(duration * FPS))
        video_chain = f"[0:v]{_still_chain(visual['motion'], num_frames)}{fade_filter}[vbase]"

    overlay = build_text_overlay(segment, safe) if visual["type"] in {"video", "photo"} else None
    if overlay is not None and overlay.getbbox():
        overlay_path = os.path.join(render_dir, f"text_{index:03d}.png")
        overlay.save(overlay_path)
        args += ["-loop", "1", "-t", f"{duration:.3f}", "-i", overlay_path]
        filter_complex = f"{video_chain};[vbase][1:v]overlay=0:0:shortest=1,format=yuv420p[vout]"
    else:
        filter_complex = f"{video_chain};[vbase]format=yuv420p[vout]"

    args += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        *FINAL_VIDEO_ARGS,
        "-t", f"{duration:.3f}",
        "-an",
        *CLEAN_METADATA_ARGS,
        out_path,
    ]
    _run_ffmpeg(args, what=f"render beat {segment.get('beat_number')}")
    return out_path


def render_preview(
    job_id: str,
    *,
    jobs_dir: str | None = None,
    out_name: str = "preview.mp4",
) -> dict[str, Any]:
    """Render preview cho job. Trả về meta output + report, ném RuntimeError/ValueError."""

    directory = os.path.join(jobs_dir or JOBS_DIR, str(job_id or ""))
    storyboard = load_job_artifact(job_id, "storyboard", jobs_dir=jobs_dir)
    if not storyboard or not storyboard.get("beats"):
        raise ValueError("STORYBOARD_MISSING")
    media_plan = load_job_artifact(job_id, "media_plan", jobs_dir=jobs_dir)
    if not media_plan or not media_plan.get("beats"):
        raise ValueError("MEDIA_PLAN_MISSING")
    manifest = load_job_artifact(job_id, "assets_manifest", jobs_dir=jobs_dir) or []

    safe = load_content_safe_zone()
    plan = build_render_plan(storyboard, media_plan, manifest, job_dir=directory, safe=safe)
    segments = plan["segments"]
    if not segments:
        raise ValueError("RENDER_PLAN_EMPTY")

    render_dir = os.path.join(directory, "render")
    os.makedirs(render_dir, exist_ok=True)

    seg_paths: list[str] = []
    try:
        seg_paths = render_segment_files(segments, render_dir=render_dir, safe=safe)

        list_path = os.path.join(render_dir, "concat.txt")
        output_path = os.path.join(directory, out_name)
        concat_segments(seg_paths, output_path, list_path=list_path)

        total = sum(float(segment["duration"]) for segment in segments)
        probe = probe_video(output_path)
        report = {
            "output": out_name,
            "mode": "preview_silent",
            "segment_count": len(segments),
            "total_planned_seconds": round(total, 2),
            "safe_zone": safe,
            "segments": [
                {
                    "beat_number": segment["beat_number"],
                    "kind": segment["kind"],
                    "visual_type": segment["visual"]["type"],
                    "asset_id": segment.get("asset_id"),
                    "duration": segment["duration"],
                    "transition": segment["transition"],
                }
                for segment in segments
            ],
            "warnings": plan["warnings"],
            "probe": probe,
        }
        _atomic_write_report(os.path.join(directory, "render_report.json"), report)
        return {"report": report, "output_path": output_path}
    finally:
        for path in seg_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.unlink(os.path.join(render_dir, "concat.txt"))
        except OSError:
            pass


def _atomic_write_report(path: str, payload: dict[str, Any]) -> None:
    import json
    import tempfile

    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp")
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def probe_video(path: str) -> dict[str, Any]:
    """ffprobe width/height/fps/codec/duration — dùng cho QA render."""

    import json as _json

    binary = os.getenv("FFPROBE_BINARY", "ffprobe")
    result = subprocess.run(
        [
            binary, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,avg_frame_rate:format=duration,size",
            "-of", "json", path,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        payload = _json.loads(result.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        fmt = payload.get("format") or {}
        num, _, den = str(stream.get("avg_frame_rate") or "0/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 0) else 0.0
        return {
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "codec": str(stream.get("codec_name") or ""),
            "fps": round(fps, 2),
            "duration": round(float(fmt.get("duration") or 0), 2),
            "size_bytes": int(fmt.get("size") or 0),
        }
    except (ValueError, KeyError, IndexError):
        return {}
