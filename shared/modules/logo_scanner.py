"""Quét logo/watermark thật trên asset bằng phân tích pixel — Giai đoạn 5.

Theo ``BRIEF_AGENT_DUNG_VIDEO_TIN_TUC.md`` §5 (phát hiện được logo/watermark
thì bỏ asset, không xử lý ảnh để che) và ``KE_HOACH_NANG_CAP_TOOL_VIDEO_TIN_TUC.md``
§8.3 (kiểm tra thật trên file, không chỉ tin cờ boolean từ crawler).

Heuristic bảo thủ, ưu tiên phát hiện hơn báo oan footage thật (asset bị loại
chỉ rơi về graphic fallback, trong khi watermark lọt qua vi phạm §8): watermark
đốt sẵn thường là chữ/icon gần trắng, viền nét, nằm dồn ở một góc — đo bằng
"tỷ lệ pixel sáng-có-cạnh" (pixel > 225 và gradient > 25) của từng góc rồi so
sánh với vùng giữa. Nhiễu loạn đều (footage dày chi tiết) có mật độ tương đương
ở mọi vùng nên bị loại bởi phép so sánh; chữ trắng ở góc vượt trội rõ rệt.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from shared.core.ffmpeg_utils import ffmpeg_command

CORNER_WIDTH_RATIO = 0.30
CORNER_HEIGHT_RATIO = 0.16
BRIGHT_EDGE_PIXEL = 225
BRIGHT_EDGE_GRADIENT = 25.0
# Góc bị coi là có watermark khi mật độ bright-edge >= max(ABS, RATIO * giữa).
# Đo trên mẫu tổng hợp: nhiễu dày đều sạch có ratio góc/giữa tối đa 1.09 (10
# seed); nền dày + chữ trắng góc ≈ 1.99 — chọn 1.6 cách đều hai phía.
BRIGHT_EDGE_ABS_THRESHOLD = 0.004
BRIGHT_EDGE_RATIO = 1.6


@dataclass(frozen=True)
class WatermarkScanResult:
    detected: bool
    score: float
    region: str

    def to_dict(self) -> dict[str, Any]:
        return {"detected": self.detected, "score": round(self.score, 4), "region": self.region}


def _grayscale(path: str) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.float32)


def _bright_edge_fraction(region: np.ndarray) -> float:
    gx = np.abs(np.diff(region, axis=1))
    gx = np.pad(gx, ((0, 0), (0, 1)))
    gy = np.abs(np.diff(region, axis=0))
    gy = np.pad(gy, ((0, 1), (0, 0)))
    bright_edges = (region > BRIGHT_EDGE_PIXEL) & ((gx + gy) > BRIGHT_EDGE_GRADIENT)
    return float(bright_edges.mean()) if bright_edges.size else 0.0


def _corner_boxes(height: int, width: int) -> list[tuple[str, slice, slice]]:
    box_w = max(8, int(width * CORNER_WIDTH_RATIO))
    box_h = max(8, int(height * CORNER_HEIGHT_RATIO))
    return [
        ("top_left", slice(0, box_h), slice(0, box_w)),
        ("top_right", slice(0, box_h), slice(width - box_w, width)),
        ("bottom_left", slice(height - box_h, height), slice(0, box_w)),
        ("bottom_right", slice(height - box_h, height), slice(width - box_w, width)),
    ]


def scan_image_pixels(image_path: str) -> WatermarkScanResult:
    """Quét 4 góc ảnh: mật độ pixel sáng-có-cạnh của góc so với vùng giữa."""

    pixels = _grayscale(image_path)
    height, width = pixels.shape
    center = _bright_edge_fraction(pixels[height // 4: 3 * height // 4, width // 4: 3 * width // 4])
    worst_name, worst_score = "", 0.0
    for name, rows, cols in _corner_boxes(height, width):
        score = _bright_edge_fraction(pixels[rows, cols])
        if score > worst_score:
            worst_name, worst_score = name, score
    threshold = max(BRIGHT_EDGE_ABS_THRESHOLD, BRIGHT_EDGE_RATIO * center)
    detected = worst_score >= threshold
    return WatermarkScanResult(detected=detected, score=round(worst_score, 4), region=worst_name if detected else "")


def scan_video_watermark(video_path: str, *, samples: int = 3, timeout: int = 120) -> WatermarkScanResult:
    """Trích vài frame trải đều video rồi quét như ảnh."""

    from shared.core.ffmpeg_utils import ffprobe_command
    import json
    import subprocess

    probe = subprocess.run(
        ffprobe_command("-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path),
        capture_output=True, text=True, timeout=30,
    )
    try:
        duration = max(0.1, float(probe.stdout.strip() or 0.1))
    except ValueError:
        duration = 0.1

    worst = WatermarkScanResult(detected=False, score=0.0, region="")
    with tempfile.TemporaryDirectory(prefix="wm_scan_") as tmp:
        for index in range(max(1, samples)):
            at = duration * (index + 0.5) / max(1, samples)
            frame_path = os.path.join(tmp, f"frame_{index}.png")
            try:
                subprocess.run(
                    ffmpeg_command("-y", "-ss", f"{at:.3f}", "-i", video_path,
                                   "-frames:v", "1", frame_path),
                    check=True, capture_output=True, timeout=timeout,
                )
            except (subprocess.SubprocessError, OSError):
                continue
            result = scan_image_pixels(frame_path)
            if result.detected and result.score > worst.score:
                worst = result
    return worst


def scan_asset_watermark(path: str, media_type: str = "video") -> WatermarkScanResult:
    """Entry point cho media planner: video quét frame, ảnh quét trực tiếp."""

    if not path or not os.path.isfile(path):
        return WatermarkScanResult(detected=False, score=0.0, region="")
    if str(media_type) == "photo":
        return scan_image_pixels(path)
    return scan_video_watermark(path)
