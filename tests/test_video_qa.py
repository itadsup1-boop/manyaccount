import unittest

from shared.core.video_qa import evaluate_video_qa


def valid_probe():
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": "30/1",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "24.0",
            "size": "2000000",
        },
    }


class VideoQATests(unittest.TestCase):
    def test_valid_video_passes(self):
        result = evaluate_video_qa(
            valid_probe(),
            analysis_log="I: -14.0 LUFS",
            decode_ok=True,
        )
        self.assertTrue(result.passed, result.blocking_errors)
        self.assertEqual(result.resolution, "1080x1920")

    def test_wrong_resolution_and_audio_are_blocking(self):
        probe = valid_probe()
        probe["streams"][0]["width"] = 720
        probe["streams"][1]["sample_rate"] = "44100"
        probe["streams"][1]["channels"] = 1
        result = evaluate_video_qa(probe, analysis_log="I: -14.0 LUFS")
        self.assertFalse(result.passed)
        self.assertIn("VIDEO_RESOLUTION_INVALID", result.blocking_errors)
        self.assertIn("AUDIO_SAMPLE_RATE_INVALID", result.blocking_errors)
        self.assertIn("AUDIO_CHANNELS_INVALID", result.blocking_errors)

    def test_decode_black_freeze_silence_and_watermark_block(self):
        result = evaluate_video_qa(
            valid_probe(),
            analysis_log=(
                "black_duration:1.2 freeze_duration:9.1 "
                "silence_duration:8.5 I: -14.0 LUFS"
            ),
            decode_ok=False,
            watermark_detected=True,
        )
        self.assertFalse(result.passed)
        self.assertIn("FFMPEG_DECODE_FAILED", result.blocking_errors)
        self.assertIn("BLACK_FRAME_DETECTED", result.blocking_errors)
        self.assertIn("FREEZE_FRAME_DETECTED", result.blocking_errors)
        self.assertIn("LONG_SILENCE_DETECTED", result.blocking_errors)
        self.assertIn("WATERMARK_DETECTED", result.blocking_errors)

    def test_small_loudness_deviation_is_warning(self):
        result = evaluate_video_qa(valid_probe(), analysis_log="I: -19.0 LUFS")
        self.assertTrue(result.passed)
        self.assertIn("LOUDNESS_WARNING", result.warnings)


if __name__ == "__main__":
    unittest.main()
