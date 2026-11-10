"""Unit test logo/watermark scanner (Giai đoạn 5) — ảnh tổng hợp qua PIL.

Case đo được khi chọn ngưỡng (xem comment ``BRIGHT_EDGE_RATIO`` trong module):
nhiễu dày đều sạch có ratio góc/giữa tối đa ~1.09, watermark góc đẩy ratio
lên ~2.0 — threshold 1.6 cách đều hai phía.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from shared.modules.logo_scanner import scan_asset_watermark, scan_image_pixels

FFMPEG_MISSING = shutil.which("ffmpeg") is None


def _noise_path(path: str, seed: int = 3) -> None:
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 255, size=(1280, 720, 3), dtype=np.uint8)
    Image.fromarray(noise).save(path)


def _flat_path(path: str, color: tuple[int, int, int]) -> None:
    canvas = np.zeros((1280, 720, 3), dtype=np.uint8)
    canvas[:, :] = color
    Image.fromarray(canvas).save(path)


def _add_watermark(path: str) -> None:
    image = Image.open(path)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    text = "SHUTTER STOCK"
    text_w = draw.textlength(text, font=font)
    draw.text(
        (image.width - text_w - 12, image.height - 70),
        text, fill=(255, 255, 255), font=font,
    )
    image.save(path)


class TestScanImagePixels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wm_scan_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_dark_background_not_detected(self):
        path = os.path.join(self.tmp, "clean_dark.jpg")
        _flat_path(path, (30, 42, 60))
        result = scan_image_pixels(path)
        self.assertFalse(result.detected)

    def test_clean_gradient_not_detected(self):
        path = os.path.join(self.tmp, "clean_grad.jpg")
        _flat_path(path, (185, 195, 210))
        result = scan_image_pixels(path)
        self.assertFalse(result.detected)

    def test_watermark_on_dark_detected(self):
        path = os.path.join(self.tmp, "wm_dark.jpg")
        _flat_path(path, (30, 42, 60))
        _add_watermark(path)
        result = scan_image_pixels(path)
        self.assertTrue(result.detected)
        self.assertEqual(result.region, "bottom_right")

    def test_watermark_on_bright_detected(self):
        path = os.path.join(self.tmp, "wm_grad.jpg")
        _flat_path(path, (185, 195, 210))
        _add_watermark(path)
        result = scan_image_pixels(path)
        self.assertTrue(result.detected)

    def test_uniform_busy_noise_not_detected(self):
        path = os.path.join(self.tmp, "busy_clean.jpg")
        _noise_path(path, seed=3)
        result = scan_image_pixels(path)
        self.assertFalse(result.detected)

    def test_watermark_on_busy_noise_detected(self):
        path = os.path.join(self.tmp, "busy_wm.jpg")
        _noise_path(path, seed=3)
        _add_watermark(path)
        result = scan_image_pixels(path)
        self.assertTrue(result.detected)

    def test_to_dict_shape(self):
        path = os.path.join(self.tmp, "clean_dark.jpg")
        _flat_path(path, (30, 42, 60))
        payload = scan_image_pixels(path).to_dict()
        self.assertEqual(set(payload), {"detected", "score", "region"})
        self.assertIsInstance(payload["detected"], bool)
        self.assertIsInstance(payload["score"], float)


class TestScanAssetWatermark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wm_asset_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_not_detected(self):
        result = scan_asset_watermark(os.path.join(self.tmp, "khong_co.mp4"), "video")
        self.assertFalse(result.detected)

    def test_photo_media_type_scans_directly(self):
        path = os.path.join(self.tmp, "wm.jpg")
        _flat_path(path, (30, 42, 60))
        _add_watermark(path)
        self.assertTrue(scan_asset_watermark(path, "photo").detected)

    @unittest.skipIf(FFMPEG_MISSING, "cần ffmpeg trong PATH")
    def test_video_scan_extracts_frames(self):
        image_path = os.path.join(self.tmp, "wm.jpg")
        _flat_path(image_path, (30, 42, 60))
        _add_watermark(image_path)
        video_path = os.path.join(self.tmp, "wm.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", image_path, "-t", "2", "-r", "10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", video_path],
            check=True, capture_output=True,
        )
        result = scan_asset_watermark(video_path, "video")
        self.assertTrue(result.detected)
        self.assertEqual(result.region, "bottom_right")


if __name__ == "__main__":
    unittest.main()
