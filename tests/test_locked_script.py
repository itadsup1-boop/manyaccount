"""Regression cho validator kịch bản khoá và job store production."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.core.locked_script import (
    DEFAULT_TARGET_DURATION_SEC,
    build_storyboard,
    profile_target_duration,
    validate_locked_script,
)
from adsup_central_hub.backend import production_jobs


def _beat(number: int, duration: float = 6.5, **overrides) -> dict:
    beat = {
        "beat_number": number,
        "role": "evidence",
        "duration_hint": duration,
        "voice_over": f"Thông tin dữ kiện số {number}.",
        "visual_query": f"authentic context b-roll {number}",
        "on_screen_text": f"Fact {number}",
        "motion": "ken_burns",
        "transition": "cut",
        "must_show": [f"con số {number}"],
    }
    beat.update(overrides)
    return beat


def _doc(**overrides) -> dict:
    doc = {
        "schema_version": 1,
        "id_tiktok": "Adsupnews",
        "source_url": "https://vnexpress.net/bai-vi-du-123.html",
        "hook": "Con số này khiến cả thị trường bất ngờ.",
        "script_voice": "Bản tin chi tiết về sự kiện đang diễn ra.",
        "music_mood": "neutral_news",
        "music_energy": 2,
        "is_sensitive": False,
        "title_tiktok": "#tinhot",
        "beats": [_beat(i) for i in range(1, 9)],
        "x_custom_future_field": {"note": "field mới do plugin thêm"},
    }
    doc.update(overrides)
    return doc


class TestProfileTarget(unittest.TestCase):
    def test_parse_profile_ranges(self):
        self.assertEqual(profile_target_duration({"video_length": "45-60s"}), 52.5)
        self.assertEqual(profile_target_duration({"video_length": "90-120s"}), 105.0)
        self.assertIsNone(profile_target_duration({"video_length": "không rõ"}))
        self.assertIsNone(profile_target_duration(None))


class TestLockedScriptValidator(unittest.TestCase):
    def test_valid_document_passes(self):
        report = validate_locked_script(_doc())
        self.assertTrue(report.passed, report.to_dict())
        self.assertEqual(report.beat_count, 8)
        self.assertAlmostEqual(report.total_hint_seconds, 52.0)
        self.assertEqual(report.errors, [])

    def test_missing_hook_blocked(self):
        report = validate_locked_script(_doc(hook=""))
        self.assertFalse(report.passed)
        codes = {issue.code for issue in report.errors}
        self.assertIn("HOOK_MISSING", codes)

    def test_missing_script_voice_blocked(self):
        report = validate_locked_script(_doc(script_voice=""))
        self.assertFalse(report.passed)
        self.assertIn(
            "SCRIPT_VOICE_MISSING", {issue.code for issue in report.errors}
        )

    def test_beat_count_blocked_both_sides(self):
        few = validate_locked_script(_doc(beats=[_beat(i) for i in range(1, 7)]))
        many = validate_locked_script(_doc(beats=[_beat(i) for i in range(1, 11)]))
        self.assertIn(
            "BEAT_COUNT_OUT_OF_RANGE", {issue.code for issue in few.errors}
        )
        self.assertIn(
            "BEAT_COUNT_OUT_OF_RANGE", {issue.code for issue in many.errors}
        )

    def test_duration_deviation_blocked_over_tolerance(self):
        report = validate_locked_script(
            _doc(beats=[_beat(i, duration=2.0) for i in range(1, 9)])
        )
        self.assertFalse(report.passed)
        self.assertIn(
            "DURATION_PROFILE_MISMATCH", {issue.code for issue in report.errors}
        )

    def test_duration_deviation_within_tolerance_passes(self):
        report = validate_locked_script(
            _doc(beats=[_beat(i, duration=7.15) for i in range(1, 9)])
        )
        self.assertTrue(report.passed, report.to_dict())

    def test_profile_target_changes_threshold(self):
        with_profile = validate_locked_script(
            _doc(beats=[_beat(i, duration=15.0) for i in range(1, 9)]),
            profile={"video_length": "90-120s"},
        )
        without_profile = validate_locked_script(
            _doc(beats=[_beat(i, duration=15.0) for i in range(1, 9)]),
        )
        self.assertTrue(with_profile.passed, with_profile.to_dict())
        self.assertFalse(without_profile.passed)
        self.assertEqual(with_profile.target_duration_seconds, 105.0)
        self.assertEqual(
            without_profile.target_duration_seconds, DEFAULT_TARGET_DURATION_SEC
        )

    def test_schema_v2_rejected(self):
        report = validate_locked_script(_doc(schema_version=2))
        self.assertFalse(report.passed)
        self.assertIn(
            "SCHEMA_VERSION_UNSUPPORTED", {issue.code for issue in report.errors}
        )

    def test_missing_schema_version_is_warning_only(self):
        doc = _doc()
        del doc["schema_version"]
        report = validate_locked_script(doc)
        self.assertTrue(report.passed)
        self.assertIn(
            "SCHEMA_VERSION_MISSING",
            {issue.code for issue in report.warnings},
        )

    def test_soft_fields_are_warnings_not_blocks(self):
        doc = _doc(
            music_mood="khong_biet",
            beats=[_beat(1, voice_over="", visual_query="")]
            + [_beat(i) for i in range(2, 9)],
        )
        del doc["id_tiktok"]
        report = validate_locked_script(doc, channel_id="")
        self.assertTrue(report.passed, report.to_dict())
        codes = {issue.code for issue in report.warnings}
        self.assertIn("MUSIC_MOOD_UNKNOWN", codes)
        self.assertIn("BEAT_VOICE_OVER_EMPTY", codes)
        self.assertIn("VISUAL_QUERY_EMPTY", codes)
        self.assertIn("CHANNEL_ID_MISSING", codes)

    def test_non_object_blocked(self):
        report = validate_locked_script([_doc()])
        self.assertFalse(report.passed)
        self.assertIn("SCRIPT_NOT_OBJECT", {issue.code for issue in report.errors})

    def test_unknown_fields_preserved_in_storyboard_source(self):
        doc = _doc()
        report = validate_locked_script(doc)
        self.assertTrue(report.passed)
        # validator không sửa JSON: field lạ phải còn nguyên trong dict gốc.
        self.assertIn("x_custom_future_field", doc)


class TestStoryboard(unittest.TestCase):
    def test_timeline_continuous_from_zero(self):
        storyboard = build_storyboard(_doc())
        self.assertEqual(storyboard["beat_count"], 8)
        self.assertAlmostEqual(storyboard["beats"][0]["start_sec"], 0.0)
        cursor = 0.0
        for beat in storyboard["beats"]:
            self.assertAlmostEqual(beat["start_sec"], round(cursor, 2))
            cursor = beat["end_sec"]
        self.assertAlmostEqual(storyboard["total_hint_seconds"], 52.0)
        self.assertEqual(storyboard["timeline_basis"], "duration_hint")

    def test_storyboard_carries_music_and_source(self):
        storyboard = build_storyboard(_doc())
        self.assertEqual(storyboard["music"]["mood"], "neutral_news")
        self.assertFalse(storyboard["music"]["is_sensitive"])
        self.assertTrue(storyboard["source_url"].startswith("https://"))
        self.assertTrue(storyboard["hook"])
        self.assertGreater(storyboard["beats"][0]["estimated_voice_seconds"], 0)


class TestProductionJobStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.jobs_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_is_idempotent_and_preserves_status(self):
        doc = _doc()
        job_id, created = production_jobs.save_job(
            doc, channel_id="Adsupnews", validation={"passed": True, "beat_count": 8},
            storyboard={"beats": []}, status="imported", jobs_dir=self.jobs_dir,
        )
        self.assertTrue(created)
        # Import lại cùng JSON phải trả lại job cũ, không đè trạng thái.
        job_id_again, created_again = production_jobs.save_job(
            doc, channel_id="Adsupnews", validation={"passed": True}, status="rendered",
            jobs_dir=self.jobs_dir,
        )
        self.assertEqual(job_id_again, job_id)
        self.assertFalse(created_again)
        meta = production_jobs.load_job(job_id, jobs_dir=self.jobs_dir)
        self.assertEqual(meta["status"], "imported")
        self.assertTrue(job_id.startswith("prod_"))

    def test_artifacts_written_and_loadable(self):
        doc = _doc()
        report = validate_locked_script(doc)
        storyboard = build_storyboard(doc, report=report)
        job_id, _ = production_jobs.save_job(
            doc,
            channel_id="Adsupnews",
            validation=report.to_dict(),
            storyboard=storyboard,
            status="imported",
            jobs_dir=self.jobs_dir,
        )
        source = production_jobs.load_job_artifact(job_id, "source", jobs_dir=self.jobs_dir)
        self.assertEqual(source["x_custom_future_field"]["note"], "field mới do plugin thêm")
        self.assertEqual(
            production_jobs.load_job_artifact(job_id, "validation", jobs_dir=self.jobs_dir)["beat_count"], 8
        )
        self.assertEqual(
            len(production_jobs.load_job_artifact(job_id, "storyboard", jobs_dir=self.jobs_dir)["beats"]), 8
        )

    def test_blocked_job_still_stored(self):
        doc = _doc(beats=[_beat(i) for i in range(1, 7)])
        report = validate_locked_script(doc)
        self.assertFalse(report.passed)
        job_id, _ = production_jobs.save_job(
            doc, channel_id="Adsupnews", validation=report.to_dict(),
            status="blocked", jobs_dir=self.jobs_dir,
        )
        meta = production_jobs.load_job(job_id, jobs_dir=self.jobs_dir)
        self.assertEqual(meta["status"], "blocked")
        self.assertFalse(meta["passed"])

    def test_path_traversal_guard(self):
        self.assertIsNone(production_jobs.load_job("../etc/passwd", jobs_dir=self.jobs_dir))
        self.assertIsNone(
            production_jobs.load_job_artifact("prod_../../x", "source", jobs_dir=self.jobs_dir)
        )
        self.assertIsNone(
            production_jobs.load_job_artifact("prod_000000000000", "not_an_artifact", jobs_dir=self.jobs_dir)
        )

    def test_list_jobs_sorted_by_created_at(self):
        first, _ = production_jobs.save_job(
            _doc(hook="Bản tin A"), channel_id="Adsupnews", status="imported", jobs_dir=self.jobs_dir,
        )
        second, _ = production_jobs.save_job(
            _doc(hook="Bản tin B"), channel_id="Adsupnews", status="imported", jobs_dir=self.jobs_dir,
        )
        items = production_jobs.list_jobs(jobs_dir=self.jobs_dir)
        ids = [item["job_id"] for item in items]
        self.assertIn(first, ids)
        self.assertIn(second, ids)
        self.assertEqual(len(ids), 2)

    def test_same_json_same_job_id(self):
        id_one, created_one = production_jobs.save_job(
            _doc(), channel_id="Adsupnews", status="imported", jobs_dir=self.jobs_dir,
        )
        id_two, created_two = production_jobs.save_job(
            _doc(), channel_id="Adsupnews", status="imported", jobs_dir=self.jobs_dir,
        )
        self.assertEqual(id_one, id_two)
        self.assertTrue(created_one)
        self.assertFalse(created_two)

    def test_source_json_round_trip_is_valid_json(self):
        job_id, _ = production_jobs.save_job(
            _doc(), channel_id="Adsupnews", status="imported", jobs_dir=self.jobs_dir,
        )
        path = Path(self.jobs_dir) / job_id / "source.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["hook"], "Con số này khiến cả thị trường bất ngờ.")


if __name__ == "__main__":
    unittest.main()
