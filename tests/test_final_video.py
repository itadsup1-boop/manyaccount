"""Unit test final_video (Giai đoạn 4).

Các hàm nhỏ (produce_voice, apply_real_timeline, build_subtitle,
build_audio_filter) test thuần Python — không gọi mạng. Riêng
``TestRenderReal`` dựng final.mp4 thật bằng ffmpeg với voice giả (sine wave
đặt sẵn trong job) — không gọi voice.adsup.vn, không cần BGM catalog.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.creator_article import final_video
from apps.creator_article.final_video import (
    MIN_SEGMENT_SECONDS,
    apply_real_timeline,
    build_audio_filter,
    build_subtitle,
    produce_voice,
    render_final_video,
)
from shared.core.channel_editorial import TARGET_VOICE_SPEED


def _make_wav(path: str, duration: float, freq: int = 440) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
            "-ar", "48000", "-ac", "1", path,
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return path


def _probe_fake(path: str) -> float:
    return 1.5 if os.path.isfile(path) and os.path.getsize(path) > 0 else 0.0


class TestProduceVoice(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="final_voice_")
        self.addCleanup(lambda: subprocess.run(
            ["rm", "-rf", self.tmp], check=False
        ))

    def test_reuses_existing_voice_without_tts(self) -> None:
        hook = _make_wav(os.path.join(self.tmp, "voice", "hook_voice.wav"), 1.0)
        script = _make_wav(os.path.join(self.tmp, "voice", "script_voice.wav"), 2.0)
        with patch.object(final_video, "probe_audio_duration", _probe_fake):
            result = produce_voice(self.tmp, "hook text", "script text", "chan")
        self.assertEqual(result["hook_path"], hook)
        self.assertEqual(result["script_path"], script)
        self.assertEqual(result["hook_duration"], 1.5)
        self.assertEqual(result["script_duration"], 1.5)
        self.assertEqual(result["total_duration"], 3.0)

    def test_missing_text_blocks_before_tts(self) -> None:
        def _fail(*args: object, **kwargs: object) -> str:
            raise AssertionError("Không được gọi TTS khi thiếu text")

        with patch.object(final_video, "probe_audio_duration", lambda path: 0.0):
            with self.assertRaises(ValueError) as ctx:
                produce_voice(self.tmp, "", "script text", "chan", tts_fn=_fail)
        self.assertIn("TTS_FAILED", str(ctx.exception))

    def test_tts_failure_raises_tts_failed(self) -> None:
        with patch.object(final_video, "probe_audio_duration", lambda path: 0.0):
            with self.assertRaises(ValueError) as ctx:
                produce_voice(self.tmp, "hook", "script", "chan", tts_fn=lambda *a, **k: None)
        self.assertIn("TTS_FAILED", str(ctx.exception))

    def test_tts_called_with_channel_profile_and_speed(self) -> None:
        calls: list[tuple] = []

        def fake_tts(text, save_dir, filename, profile_id, speed=1.0):
            calls.append((text, save_dir, filename, profile_id, speed))
            path = os.path.join(save_dir, filename)
            with open(path, "wb") as handle:
                handle.write(b"fake")
            return path

        with patch.object(final_video, "probe_audio_duration", _probe_fake):
            result = produce_voice(self.tmp, "hook", "script", "chan", tts_fn=fake_tts)
        self.assertEqual([call[:3] for call in calls], [
            ("hook", os.path.join(self.tmp, "voice"), "hook_voice.wav"),
            ("script", os.path.join(self.tmp, "voice"), "script_voice.wav"),
        ])
        profile_id = final_video.resolve_voice_profile("chan")
        self.assertEqual({call[3] for call in calls}, {profile_id})
        self.assertEqual({call[4] for call in calls}, {TARGET_VOICE_SPEED})
        self.assertEqual(result["total_duration"], 3.0)


class TestApplyRealTimeline(unittest.TestCase):
    def test_applies_real_durations(self) -> None:
        segments = [{"duration": 9.0, "start_sec": 0.0, "transition": "cut"},
                    {"duration": 9.0, "start_sec": 9.0, "transition": "cut"}]
        timeline = SimpleNamespace(segments=[
            SimpleNamespace(duration=2.3456, start=0.0, transition="cut"),
            SimpleNamespace(duration=1.6544, start=2.3456, transition="fade"),
        ])
        result = apply_real_timeline(segments, timeline)
        self.assertEqual(result[0]["duration"], 2.346)
        self.assertEqual(result[1]["start_sec"], 2.346)
        self.assertEqual(result[1]["transition"], "fade")

    def test_min_duration_clamp(self) -> None:
        segments = [{"duration": 9.0, "start_sec": 0.0, "transition": "cut"}]
        timeline = SimpleNamespace(segments=[SimpleNamespace(duration=0.01, start=0.0, transition="")])
        result = apply_real_timeline(segments, timeline)
        self.assertEqual(result[0]["duration"], MIN_SEGMENT_SECONDS)
        self.assertEqual(result[0]["transition"], "cut")

    def test_length_mismatch_raises(self) -> None:
        timeline = SimpleNamespace(segments=[SimpleNamespace(duration=1.0, start=0.0, transition="cut")])
        with self.assertRaises(ValueError) as ctx:
            apply_real_timeline([{}, {}, {}], timeline)
        self.assertIn("TIMELINE_MISMATCH", str(ctx.exception))


class TestBuildSubtitle(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="final_subs_")
        self.addCleanup(lambda: subprocess.run(
            ["rm", "-rf", self.tmp], check=False
        ))

    def test_json_text_primary_engine(self) -> None:
        path, engine = build_subtitle(
            self.tmp, script_voice_path="a.wav",
            script_text="TP.HCM nâng trần phí quản lý lên 13.700 đồng/m2.",
            hook_duration=1.2, script_duration=3.0,
            keywords=["13.700"], id_tiktok="chan",
        )
        self.assertEqual(engine, "text")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as handle:  # type: ignore[arg-type]
            content = handle.read()
        self.assertIn("Dialogue:", content)
        self.assertIn("13.700", content)

    def test_whisper_fallback_when_script_text_empty(self) -> None:
        ass = os.path.join(self.tmp, "subs.ass")
        with open(ass, "w", encoding="utf-8") as handle:
            handle.write("[Script Info]\n")

        def fake_word_ass(audio, out, **kwargs):
            self.assertEqual(out, ass)
            self.assertEqual(kwargs["keywords"], ["2 tỷ"])
            return ass

        with patch.object(final_video, "generate_word_ass", fake_word_ass):
            path, engine = build_subtitle(
                self.tmp, script_voice_path="a.wav", script_text="",
                hook_duration=1.2, script_duration=3.0,
                keywords=["2 tỷ"], id_tiktok="chan",
            )
        self.assertEqual((path, engine), (ass, "whisper"))

    def test_no_subtitle_when_everything_fails(self) -> None:
        with patch.object(final_video, "generate_word_ass", lambda *a, **k: None):
            path, engine = build_subtitle(
                self.tmp, script_voice_path="a.wav", script_text="",
                hook_duration=1.2, script_duration=3.0,
                keywords=[], id_tiktok="chan",
            )
        self.assertIsNone(path)
        self.assertEqual(engine, "none")


class TestBuildAudioFilter(unittest.TestCase):
    def test_voice_only_uses_loudnorm(self) -> None:
        audio_filter, label = build_audio_filter(has_bgm=False, bgm_input_index=3, total_duration=10.0)
        self.assertEqual(
            audio_filter,
            "[1:a][2:a]concat=n=2:v=0:a=1[a_voice];[a_voice]loudnorm=I=-14:LRA=9:TP=-1.5[a_merged]",
        )
        self.assertEqual(label, "a_merged")

    def test_bgm_ducking(self) -> None:
        selection = SimpleNamespace(cue_start_sec=0.5, bed_gain_db=-6.0)
        audio_filter, label = build_audio_filter(
            has_bgm=True, bgm_input_index=3, total_duration=10.0, selection=selection,
        )
        self.assertIn("[3:a]", audio_filter)
        self.assertIn("sidechaincompress", audio_filter)
        self.assertIn("final_music", audio_filter)
        self.assertEqual(label, "a_merged")

    def test_sfx_delay_and_mix(self) -> None:
        cues = [SimpleNamespace(timestamp=2.5, gain=0.8)]
        audio_filter, label = build_audio_filter(
            has_bgm=True, bgm_input_index=3, total_duration=10.0,
            selection=SimpleNamespace(cue_start_sec=0.0, bed_gain_db=-6.0),
            sfx_cues=cues, sfx_input_start=4,
        )
        self.assertIn("[4:a]adelay=2500|2500,volume=0.80[sfx0]", audio_filter)
        self.assertIn("amix=inputs=2:duration=first", audio_filter)
        self.assertIn("alimiter=limit=0.84", audio_filter)
        self.assertEqual(label, "a_out")


def _storyboard() -> dict:
    return {
        "schema_version": 1,
        "hook": "Giá xăng hôm nay tăng mạnh.",
        "script_voice": "Bản ghi chính dài hơn một chút để có thời lượng thật. Kết thúc có payoff.",
        "music": {"mood": "neutral_news", "energy": 2, "is_sensitive": True},
        "beats": [
            {
                "beat_number": 1, "role": "hook",
                "start_sec": 0.0, "end_sec": 1.5, "duration_hint": 1.5,
                "voice_over": "Giá xăng hôm nay tăng mạnh.",
                "visual_query": "DATA GRAPHIC: giá xăng",
                "on_screen_text": "GIÁ XĂNG TĂNG",
                "must_show": ["GIÁ XĂNG TĂNG"],
                "motion": "slow_push_in", "transition": "cut",
            },
            {
                "beat_number": 2, "role": "development",
                "start_sec": 1.5, "end_sec": 3.0, "duration_hint": 2.0,
                "voice_over": "Bản ghi chính dài hơn một chút để có thời lượng thật.",
                "visual_query": "people at fuel station",
                "on_screen_text": "+2%",
                "must_show": ["+2%"],
                "motion": "static", "transition": "cut",
            },
            {
                "beat_number": 3, "role": "payoff",
                "start_sec": 3.0, "end_sec": 4.0, "duration_hint": 1.5,
                "voice_over": "Kết thúc có payoff.",
                "visual_query": "money savings",
                "on_screen_text": "THEO DÕI",
                "must_show": [],
                "motion": "static", "transition": "cut",
            },
        ],
    }


def _write_job(jobs_dir: str, job_id: str, *, with_storyboard: bool = True, with_plan: bool = True) -> str:
    directory = os.path.join(jobs_dir, job_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "job.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "job_id": job_id,
            "channel_id": "id_tiktok_test",
            "id_tiktok": "id_tiktok_test",
            "status": "assets_ready",
            "passed": True,
            "beat_count": 3,
        }, handle, ensure_ascii=False)
    if with_storyboard:
        with open(os.path.join(directory, "storyboard.json"), "w", encoding="utf-8") as handle:
            json.dump(_storyboard(), handle, ensure_ascii=False)
    if with_plan:
        with open(os.path.join(directory, "media_plan.json"), "w", encoding="utf-8") as handle:
            json.dump({
                "beats": [
                    {"beat_number": 1, "kind": "no_asset", "asset_id": None},
                    {"beat_number": 2, "kind": "data_graphic", "asset_id": None},
                    {"beat_number": 3, "kind": "no_asset", "asset_id": None},
                ]
            }, handle, ensure_ascii=False)
        with open(os.path.join(directory, "assets_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump([], handle)
    return directory


def _fake_selection(license_status: str, bgm_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        track_id="bgm_test", path=bgm_path, mood="neutral_news", energy=2,
        cue_start_sec=0.0, bed_lufs=-22.0, license_status=license_status,
        license_source="test", bed_gain_db=-6.0,
    )


@unittest.skipUnless(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0,
    "cần ffmpeg trong PATH",
)
class TestRenderReal(unittest.TestCase):
    """Dựng final.mp4 thật (voice giả 4s, BGM giả) — bắt lỗi filtergraph."""

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="final_render_")
        self.addCleanup(lambda: subprocess.run(
            ["rm", "-rf", tmp], check=False
        ))
        self.jobs_dir = tmp
        self.job_id = "prod_0123456789ab"
        directory = _write_job(tmp, self.job_id)
        _make_wav(os.path.join(directory, "voice", "hook_voice.wav"), 1.0, freq=520)
        _make_wav(os.path.join(directory, "voice", "script_voice.wav"), 3.0, freq=440)
        self.bgm_path = _make_wav(os.path.join(tmp, "bgm_test.wav"), 2.0, freq=220)
        # Bỏ whisper để e2e chạy nhanh/deterministic — fallback text được test riêng.
        patcher = patch.object(final_video, "generate_word_ass", lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _render_with_license(self, license_status: str) -> dict:
        selection = _fake_selection(license_status, self.bgm_path)
        with patch.object(final_video, "select_music", lambda *a, **k: selection):
            return render_final_video(self.job_id, jobs_dir=self.jobs_dir)

    def test_missing_storyboard_blocks(self) -> None:
        _write_job(self.jobs_dir, "prod_111111111111", with_storyboard=False)
        with self.assertRaises(ValueError) as ctx:
            render_final_video("prod_111111111111", jobs_dir=self.jobs_dir)
        self.assertIn("STORYBOARD_MISSING", str(ctx.exception))

    def test_missing_media_plan_blocks(self) -> None:
        _write_job(self.jobs_dir, "prod_222222222222", with_plan=False)
        with self.assertRaises(ValueError) as ctx:
            render_final_video("prod_222222222222", jobs_dir=self.jobs_dir)
        self.assertIn("MEDIA_PLAN_MISSING", str(ctx.exception))

    def test_render_final_end_to_end(self) -> None:
        result = self._render_with_license("approved")
        report = result["report"]
        output = result["output_path"]

        self.assertTrue(os.path.isfile(output))
        self.assertEqual(report["mode"], "final")
        self.assertEqual(report["timeline_source"], "tts_real")
        self.assertEqual(report["segment_count"], 3)
        self.assertEqual(report["voice"]["hook_duration"], 1.0)
        self.assertEqual(report["voice"]["script_duration"], 3.0)
        self.assertEqual(report["voice"]["total_duration"], 4.0)
        self.assertEqual(report["bgm"]["track_id"], "bgm_test")
        self.assertEqual(report["bgm"]["license_status"], "approved")
        self.assertEqual(report["subtitle"]["engine"], "text")
        self.assertEqual(report["sfx_count"], 0)

        probe = report["probe"]
        self.assertEqual(probe["codec"], "h264")
        self.assertAlmostEqual(probe["duration"], 4.0, delta=1.0)

        audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", output],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(audio.stdout.strip(), "aac")

        report_path = os.path.join(self.jobs_dir, self.job_id, "final_report.json")
        with open(report_path, encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["mode"], "final")
        self.assertEqual(saved["voice"]["total_duration"], 4.0)

    def test_unapproved_license_skips_bgm(self) -> None:
        result = self._render_with_license("pending")
        report = result["report"]
        self.assertIsNone(report["bgm"])
        self.assertTrue(any("license_status=pending" in w for w in report["warnings"]))
        # Không BGM vẫn phải có audio aac (voice only + loudnorm).
        audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", result["output_path"]],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(audio.stdout.strip(), "aac")


if __name__ == "__main__":
    unittest.main()
