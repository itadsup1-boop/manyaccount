import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from shared.services.music_selector import (
    build_ducked_mix_filter,
    discover_music_tracks,
    normalize_music_mood,
    select_music,
)


class MusicSelectorTests(unittest.TestCase):
    def test_normalize_music_mood_uses_tone_and_sensitive_override(self):
        self.assertEqual(normalize_music_mood(None, tone="Tích cực"), "positive_upbeat")
        self.assertEqual(
            normalize_music_mood("breaking_tension", is_sensitive=True),
            "sensitive_empathy",
        )
        self.assertEqual(normalize_music_mood("unknown", tone="Cảnh báo"), "serious_warning")

    def test_catalog_discovery_and_recent_repeat_avoidance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bgm_dir = tmp_path / "bgm"
            mood_dir = bgm_dir / "neutral_news"
            mood_dir.mkdir(parents=True)
            for name in ("one.mp3", "two.mp3"):
                (mood_dir / name).write_bytes(b"test")

            catalog = {
                "tracks": [
                    {
                        "id": "one",
                        "file": "neutral_news/one.mp3",
                        "moods": ["neutral_news"],
                        "energy": 2,
                        "cue_start_sec": 3.5,
                        "license_status": "approved",
                        "license_source": "test-license-one.txt",
                    },
                    {
                        "id": "two",
                        "file": "neutral_news/two.mp3",
                        "moods": ["neutral_news"],
                        "energy": 2,
                        "license_status": "approved",
                        "license_source": "test-license-two.txt",
                    },
                ]
            }
            (bgm_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            history_path = tmp_path / "history.json"

            tracks = discover_music_tracks(bgm_dir)
            self.assertEqual({track.track_id for track in tracks}, {"one", "two"})

            first = select_music(
                "neutral_news",
                channel_id="channel-a",
                bgm_dir=bgm_dir,
                history_path=history_path,
                recent_limit=1,
            )
            second = select_music(
                "neutral_news",
                channel_id="channel-a",
                bgm_dir=bgm_dir,
                history_path=history_path,
                recent_limit=1,
            )

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first.track_id, second.track_id)

    def test_unverified_music_is_not_selected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bgm_dir = tmp_path / "bgm"
            mood_dir = bgm_dir / "neutral_news"
            mood_dir.mkdir(parents=True)
            (mood_dir / "unknown.mp3").write_bytes(b"test")
            (bgm_dir / "catalog.json").write_text(
                json.dumps({
                    "tracks": [{
                        "id": "unknown",
                        "file": "neutral_news/unknown.mp3",
                        "moods": ["neutral_news"],
                        "license_status": "unverified",
                    }]
                }),
                encoding="utf-8",
            )

            self.assertIsNone(select_music(
                "neutral_news",
                bgm_dir=bgm_dir,
                history_path=tmp_path / "history.json",
            ))

    def test_sensitive_mood_never_falls_back_to_upbeat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bgm_dir = tmp_path / "bgm"
            mood_dir = bgm_dir / "positive_upbeat"
            mood_dir.mkdir(parents=True)
            (mood_dir / "happy.mp3").write_bytes(b"test")

            selection = select_music(
                "breaking_tension",
                is_sensitive=True,
                bgm_dir=bgm_dir,
                history_path=tmp_path / "history.json",
            )
            self.assertIsNone(selection)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_ffmpeg_duck_mix_smoke(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            voice_path = tmp_path / "voice.wav"
            output_path = tmp_path / "mixed.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=3",
                    "-c:a", "pcm_s16le", str(voice_path),
                ],
                check=True,
                capture_output=True,
            )
            selection = select_music(
                "neutral_news",
                channel_id="ffmpeg-smoke",
                history_path=tmp_path / "history.json",
            )
            if selection is None:
                self.skipTest("No local neutral_news music asset")

            graph = build_ducked_mix_filter(
                "0:a",
                "1:a",
                3.0,
                selection,
                output_label="aout",
                label_prefix="test_music",
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(voice_path),
                    "-stream_loop", "-1", "-i", selection.path,
                    "-filter_complex", graph,
                    "-map", "[aout]", "-t", "3",
                    "-c:a", "pcm_s16le", str(output_path),
                ],
                check=True,
                capture_output=True,
            )
            self.assertGreater(output_path.stat().st_size, 1_000)


if __name__ == "__main__":
    unittest.main()
