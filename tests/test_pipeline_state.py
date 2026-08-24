import unittest

from shared.core.pipeline_state import (
    PipelineLifecycle,
    PipelineStageError,
)


class PipelineStateTests(unittest.TestCase):
    def test_lifecycle_advances_and_rejects_backward_transition(self):
        lifecycle = PipelineLifecycle("article", "item-1")
        lifecycle.advance("scripted")
        lifecycle.advance("validated")
        with self.assertRaises(ValueError):
            lifecycle.advance("selected")
        self.assertEqual(lifecycle.status, "validated")

    def test_structured_failure_has_stage_code_and_retryable(self):
        lifecycle = PipelineLifecycle("facebook", "item-2")
        lifecycle.advance("scripted")
        failure = lifecycle.fail_from_exception(
            PipelineStageError(
                "validated",
                "EVIDENCE_VALIDATION_FAILED",
                "Thiếu nguồn",
            )
        )
        self.assertEqual(failure.status, "failed")
        self.assertEqual(failure.stage, "validated")
        self.assertFalse(failure.retryable)
        self.assertEqual(lifecycle.event()["error_code"], "EVIDENCE_VALIDATION_FAILED")

    def test_unknown_exception_uses_current_stage_default(self):
        lifecycle = PipelineLifecycle("tiktok", "item-3")
        lifecycle.advance("rendered")
        failure = lifecycle.fail_from_exception(RuntimeError("ffmpeg stopped"))
        self.assertEqual(failure.error_code, "RENDER_FAILED")
        self.assertTrue(failure.retryable)


if __name__ == "__main__":
    unittest.main()
