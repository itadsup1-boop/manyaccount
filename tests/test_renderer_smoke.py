"""Opt-in QA smoke checks for real outputs from all production render modes.

Set RENDERER_SMOKE_DIR to a directory containing the five filenames below.
The test is opt-in because rendering fixtures needs FFmpeg and several large media
assets; CI/unit runs should not silently upload or download production media.
"""

import os
import shutil
import unittest

from shared.core.video_qa import run_video_qa


SMOKE_DIR = os.environ.get("RENDERER_SMOKE_DIR", "")


@unittest.skipUnless(SMOKE_DIR and shutil.which("ffmpeg"), "set RENDERER_SMOKE_DIR")
class RendererOutputSmokeTests(unittest.TestCase):
    def _assert_passes(self, filename, subtitle_filename=""):
        video_path = os.path.join(SMOKE_DIR, filename)
        subtitle_path = (
            os.path.join(SMOKE_DIR, subtitle_filename) if subtitle_filename else ""
        )
        self.assertTrue(os.path.exists(video_path), video_path)
        result = run_video_qa(video_path, subtitle_ass_path=subtitle_path)
        self.assertTrue(result.passed, result.to_dict())

    def test_article(self):
        self._assert_passes("article_phase5.mp4", "article_phase5_body.ass")

    def test_facebook_with_frame(self):
        self._assert_passes("final_phase5.mp4", "subtitle_phase5.ass")

    def test_facebook_without_frame(self):
        self._assert_passes("final_phase5_noframe.mp4")

    def test_tiktok_full_remix(self):
        self._assert_passes("remix_phase5.mp4")

    def test_tiktok_original_audio(self):
        self._assert_passes("remix_phase5_original.mp4")


if __name__ == "__main__":
    unittest.main()
