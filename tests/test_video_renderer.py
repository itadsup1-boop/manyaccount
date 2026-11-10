"""Unit test video_renderer (Giai đoạn 3).

Phần lớn test là thuần Python (không ffmpeg). Riêng ``TestRenderReal`` render
thật một preview nhỏ (2 giây) để bắt lỗi filtergraph — cần ffmpeg trong PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsup_central_hub.backend import production_jobs
from apps.creator_article.video_renderer import (
    build_data_graphic_card,
    build_fact_card,
    build_map_graphic_card,
    build_quote_card,
    build_render_plan,
    build_text_overlay,
    build_typography_card,
    load_content_safe_zone,
    render_preview,
    wrap_text,
    _load_font,
    _segment_duration,
)

SAFE = {"left": 60, "top": 150, "right": 900, "bottom": 1500}


def _beat(n: int, visual_query: str, **extra: object) -> dict:
    beat = {
        "beat_number": n,
        "role": "fact",
        "start_sec": (n - 1) * 6.5,
        "end_sec": n * 6.5,
        "duration_hint": 6.5,
        "voice_over": f"voice {n}",
        "visual_query": visual_query,
        "on_screen_text": f"Chữ {n}",
        "motion": "cut",
        "transition": "cut",
        "must_show": [],
    }
    beat.update(extra)
    return beat


def _manifest_entry(asset_id: str, ext: str, media_type: str, **extra: object) -> dict:
    """Manifest record đủ field provenance/license/scan (KE_HOACH §8 yêu cầu)."""

    entry = {
        "asset_id": asset_id,
        "local_path": f"assets/{asset_id}.{ext}",
        "media_type": media_type,
        "provider": "pexels",
        "provider_asset_id": f"pexels_{media_type}_{asset_id}",
        "asset_url": f"http://cdn/{asset_id}_1080.{ext}",
        "page_url": f"https://www.pexels.com/{media_type}/{asset_id}",
        "license_status": "licensed",
        "license_source": "pexels_license",
        "logo_scan": "passed",
        "watermark_scan": {"detected": False, "score": 0.0, "region": ""},
    }
    entry.update(extra)
    return entry


class TestSafeZone(unittest.TestCase):
    def test_loads_project_config(self):
        self.assertEqual(
            load_content_safe_zone(),
            {"left": 60, "top": 150, "right": 900, "bottom": 1500},
        )

    def test_fallback_when_config_missing(self):
        zone = load_content_safe_zone("/khong/ton/tai/video_safe_zones.json")
        self.assertEqual(zone, {"left": 72, "top": 180, "right": 1008, "bottom": 1560})


class TestWrapText(unittest.TestCase):
    def test_wraps_within_width(self):
        font = _load_font(64)
        lines = wrap_text("Phố trắng đêm muộn xe cộ tấp nập", font, 500, max_lines=2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(font.getlength(line) <= 500 for line in lines))

    def test_empty_text(self):
        self.assertEqual(wrap_text("", _load_font(48), 500), [])


class TestSegmentDuration(unittest.TestCase):
    def test_uses_start_end(self):
        self.assertEqual(_segment_duration({"start_sec": 2, "end_sec": 8.5}), 6.5)

    def test_falls_back_to_hint(self):
        self.assertEqual(_segment_duration({"start_sec": 0, "end_sec": 0, "duration_hint": 3}), 3.0)

    def test_clamps_tiny_beats(self):
        self.assertEqual(_segment_duration({"start_sec": 0, "end_sec": 0.1}), 0.5)


class TestBuildRenderPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="render_plan_test_")
        os.makedirs(os.path.join(self.tmp, "assets"))
        self.video_path = os.path.join(self.tmp, "assets", "stock_002.mp4")
        self.photo_path = os.path.join(self.tmp, "assets", "stock_004.jpg")
        open(self.video_path, "wb").write(b"\x00")
        open(self.photo_path, "wb").write(b"\x00")
        self.manifest = [_manifest_entry("stock_002", "mp4", "video"), _manifest_entry("stock_004", "jpg", "photo")]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, beats, plan_beats, manifest=None):
        storyboard = {"beats": beats}
        media_plan = {"beats": plan_beats}
        return build_render_plan(
            storyboard, media_plan, manifest if manifest is not None else self.manifest,
            job_dir=self.tmp, safe=SAFE,
        )

    def test_all_kinds_mapped(self):
        beats = [
            _beat(1, "DATA GRAPHIC: 2 tỷ", on_screen_text="2 tỷ"),
            _beat(2, "people walking", transition="fade"),
            _beat(3, "quantum physics"),
            _beat(4, "MAP GRAPHIC: ha noi", on_screen_text="Bản đồ"),
        ]
        plan_beats = [
            {"beat_number": 1, "kind": "data_graphic"},
            {"beat_number": 2, "kind": "broll", "asset_id": "stock_002"},
            {"beat_number": 3, "kind": "no_asset_found"},
            {"beat_number": 4, "kind": "map_graphic"},
        ]
        plan = self._plan(beats, plan_beats)
        kinds = [s["kind"] for s in plan["segments"]]
        self.assertEqual(kinds, ["data_graphic", "broll", "no_asset_found", "map_graphic"])
        self.assertEqual(plan["segments"][1]["visual"]["type"], "video")
        self.assertEqual(plan["segments"][1]["visual"]["path"], self.video_path)
        self.assertEqual(plan["segments"][1]["transition"], "fade")
        self.assertEqual(plan["segments"][0]["visual"]["type"], "card")
        self.assertEqual(plan["segments"][3]["asset_id"], None)

    def test_photo_broll_resolved(self):
        plan = self._plan(
            [_beat(1, "people walking")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_004"}],
        )
        segment = plan["segments"][0]
        self.assertEqual(segment["visual"]["type"], "photo")
        self.assertEqual(segment["visual"]["path"], self.photo_path)

    def test_asset_id_not_in_manifest_blocks_render(self):
        with self.assertRaises(ValueError) as ctx:
            self._plan(
                [_beat(1, "people walking")],
                [{"beat_number": 1, "kind": "broll", "asset_id": "stock_999"}],
            )
        self.assertTrue(str(ctx.exception).startswith("PROVENANCE_MISSING"))

    def test_unlicensed_asset_excluded_to_graphic_fallback(self):
        plan = self._plan(
            [_beat(1, "people walking")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_002"}],
            manifest=[_manifest_entry("stock_002", "mp4", "video", license_status="unknown")],
        )
        segment = plan["segments"][0]
        self.assertEqual(segment["kind"], "no_asset_found")
        self.assertEqual(segment["visual"]["type"], "card")
        self.assertTrue(any("rights_guard_failed" in w for w in plan["warnings"]))

    def test_asset_without_provenance_excluded(self):
        plan = self._plan(
            [_beat(1, "people walking")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_002"}],
            manifest=[_manifest_entry("stock_002", "mp4", "video", asset_url="", page_url="")],
        )
        self.assertEqual(plan["segments"][0]["kind"], "no_asset_found")
        self.assertTrue(any("rights_guard_failed" in w for w in plan["warnings"]))

    def test_watermark_detected_asset_excluded(self):
        plan = self._plan(
            [_beat(1, "people walking")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_002"}],
            manifest=[
                _manifest_entry(
                    "stock_002", "mp4", "video",
                    watermark_scan={"detected": True, "score": 0.03, "region": "bottom_right"},
                )
            ],
        )
        self.assertEqual(plan["segments"][0]["kind"], "no_asset_found")
        self.assertTrue(any("watermark_detected" in w for w in plan["warnings"]))

    def test_unscanned_asset_excluded(self):
        plan = self._plan(
            [_beat(1, "people walking")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_002"}],
            manifest=[_manifest_entry("stock_002", "mp4", "video", logo_scan="pending", watermark_scan="pending")],
        )
        self.assertEqual(plan["segments"][0]["kind"], "no_asset_found")
        self.assertTrue(any("watermark_scan_missing" in w for w in plan["warnings"]))

    def test_text_fields_pass_through_to_cards(self):
        plan = self._plan(
            [
                _beat(
                    1,
                    "DATA GRAPHIC: so sánh 2 tỷ đồng",
                    on_screen_text="2 tỷ đồng",
                    must_show=["2 tỷ đồng"],
                )
            ],
            [{"beat_number": 1, "kind": "data_graphic"}],
        )
        segment = plan["segments"][0]
        self.assertEqual(segment["visual_query"], "DATA GRAPHIC: so sánh 2 tỷ đồng")
        self.assertEqual(segment["on_screen_text"], "2 tỷ đồng")
        self.assertEqual(segment["must_show"], ["2 tỷ đồng"])

    def test_video_motion_defaults_static(self):
        plan = self._plan(
            [_beat(1, "people walking", motion="cut")],
            [{"beat_number": 1, "kind": "broll", "asset_id": "stock_002"}],
        )
        self.assertEqual(plan["segments"][0]["visual"]["motion"], "static")


class TestGraphicCards(unittest.TestCase):
    def test_cards_full_canvas(self):
        beat = {
            "on_screen_text": "2 tỷ đồng", "must_show": ["2 tỷ đồng", "3 căn"],
            "visual_query": "DATA GRAPHIC: 2 tỷ đồng",
        }
        for builder in (
            build_data_graphic_card,
            build_map_graphic_card,
            build_typography_card,
            build_quote_card,
            build_fact_card,
        ):
            image = builder(beat, SAFE)
            self.assertEqual(image.size, (1080, 1920), builder.__name__)

    def test_typography_card_uses_query_when_no_headline(self):
        image = build_typography_card({"on_screen_text": "", "visual_query": "câu lạc bộ bóng đá"}, SAFE)
        colors = image.getcolors(maxcolors=1 << 20)
        self.assertTrue(colors)  # có nội dung vẽ

    def test_text_overlay_bbox(self):
        with_text = build_text_overlay({"on_screen_text": "Phố trắng"}, SAFE)
        self.assertTrue(with_text.getbbox())
        without = build_text_overlay({"on_screen_text": ""}, SAFE)
        self.assertFalse(without.getbbox())


class TestRenderPreviewGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="render_guard_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_storyboard_missing(self):
        job_id, _ = production_jobs.save_job(
            {"x": 1}, channel_id="t", validation={"passed": True}, jobs_dir=self.tmp,
        )
        with self.assertRaises(ValueError) as ctx:
            render_preview(job_id, jobs_dir=self.tmp)
        self.assertEqual(str(ctx.exception), "STORYBOARD_MISSING")

    def test_media_plan_missing(self):
        job_id, _ = production_jobs.save_job(
            {"x": 1}, channel_id="t", validation={"passed": True},
            storyboard={"beats": [_beat(1, "x")]}, jobs_dir=self.tmp,
        )
        with self.assertRaises(ValueError) as ctx:
            render_preview(job_id, jobs_dir=self.tmp)
        self.assertEqual(str(ctx.exception), "MEDIA_PLAN_MISSING")


class TestJobFilePath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jobfile_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_existing_file(self):
        job_id, _ = production_jobs.save_job({"x": 1}, channel_id="t", jobs_dir=self.tmp)
        from adsup_central_hub.backend.production_jobs import _atomic_write_json
        _atomic_write_json(os.path.join(self.tmp, job_id, "preview.mp4.txt"), {"a": 1})
        path = production_jobs.job_file_path(job_id, "preview.mp4.txt", jobs_dir=self.tmp)
        self.assertTrue(path and os.path.isfile(path))

    def test_rejects_traversal_and_missing(self):
        self.assertIsNone(production_jobs.job_file_path("../../etc", "passwd", jobs_dir=self.tmp))
        job_id, _ = production_jobs.save_job({"x": 1}, channel_id="t", jobs_dir=self.tmp)
        self.assertIsNone(production_jobs.job_file_path(job_id, "khong_co.txt", jobs_dir=self.tmp))


class TestRenderReal(unittest.TestCase):
    """Render thật 2 giây — bắt lỗi filtergraph, concat, ffprobe."""

    def test_render_two_segments(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg không có trong PATH")
        tmp = tempfile.mkdtemp(prefix="render_real_test_")
        try:
            jobs = os.path.join(tmp, "jobs")
            storyboard = {"beats": [
                _beat(1, "DATA GRAPHIC: 2 tỷ đồng", on_screen_text="2 tỷ đồng",
                      must_show=["2 tỷ đồng"], start_sec=0, end_sec=1.0, duration_hint=1.0),
                _beat(2, "people walking", on_screen_text="Phố trắng",
                      start_sec=1.0, end_sec=2.0, duration_hint=1.0, transition="fade"),
            ]}
            media_plan = {"beats": [
                {"beat_number": 1, "kind": "data_graphic"},
                {"beat_number": 2, "kind": "broll", "asset_id": "stock_002"},
            ]}
            manifest = [_manifest_entry("stock_002", "mp4", "video")]
            job_id, _ = production_jobs.save_job(
                {"x": 1}, channel_id="t", validation={"beat_count": 2, "passed": True},
                storyboard=storyboard, jobs_dir=jobs,
            )
            job_dir = os.path.join(jobs, job_id)
            os.makedirs(os.path.join(job_dir, "assets"))
            from adsup_central_hub.backend.production_jobs import _atomic_write_json
            _atomic_write_json(os.path.join(job_dir, "media_plan.json"), media_plan)
            _atomic_write_json(os.path.join(job_dir, "assets_manifest.json"), manifest)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=2",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                 os.path.join(job_dir, "assets", "stock_002.mp4")],
                check=True, capture_output=True,
            )

            result = render_preview(job_id, jobs_dir=jobs)
            probe = result["report"]["probe"]
            self.assertEqual(probe["width"], 1080)
            self.assertEqual(probe["height"], 1920)
            self.assertEqual(probe["codec"], "h264")
            self.assertAlmostEqual(probe["fps"], 30.0, delta=0.01)
            self.assertAlmostEqual(probe["duration"], 2.0, delta=0.3)
            self.assertTrue(os.path.isfile(os.path.join(job_dir, "render_report.json")))
            self.assertTrue(os.path.isfile(os.path.join(job_dir, "preview.mp4")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
