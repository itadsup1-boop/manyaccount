"""Shared pipeline lifecycle and structured failure payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PIPELINE_STAGES = (
    "selected",
    "scripted",
    "validated",
    "voiced",
    "rendered",
    "qa_passed",
    "uploaded",
    "published",
    "measured",
)

DEFAULT_ERROR_CODES = {
    "selected": "SOURCE_SELECTION_FAILED",
    "scripted": "SCRIPT_GENERATION_FAILED",
    "validated": "CONTENT_VALIDATION_FAILED",
    "voiced": "TTS_FAILED",
    "rendered": "RENDER_FAILED",
    "qa_passed": "VIDEO_QA_FAILED",
    "uploaded": "UPLOAD_FAILED",
    "published": "PUBLISH_FAILED",
    "measured": "METRICS_FAILED",
}

NON_RETRYABLE_CODES = {
    "CONTENT_VALIDATION_FAILED",
    "EVIDENCE_VALIDATION_FAILED",
    "RIGHTS_VALIDATION_FAILED",
    "SAFE_ZONE_FAILED",
    "WATERMARK_DETECTED",
}


@dataclass(frozen=True)
class PipelineFailure:
    status: str
    stage: str
    error_code: str
    retryable: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineStageError(RuntimeError):
    def __init__(
        self,
        stage: str,
        error_code: str,
        message: str,
        *,
        retryable: bool | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.retryable = (
            error_code not in NON_RETRYABLE_CODES
            if retryable is None
            else bool(retryable)
        )


class PipelineLifecycle:
    def __init__(self, pipeline: str, item_id: str = ""):
        self.pipeline = str(pipeline or "unknown")
        self.item_id = str(item_id or "")
        self.status = "selected"
        self.history = ["selected"]
        self.failure: PipelineFailure | None = None

    def advance(self, stage: str) -> str:
        if stage not in PIPELINE_STAGES:
            raise ValueError(f"Unknown pipeline stage: {stage}")
        if self.failure:
            raise ValueError("Cannot advance a failed pipeline")
        current_index = PIPELINE_STAGES.index(self.status)
        target_index = PIPELINE_STAGES.index(stage)
        if target_index < current_index:
            raise ValueError(f"Pipeline cannot move backward: {self.status} -> {stage}")
        self.status = stage
        if not self.history or self.history[-1] != stage:
            self.history.append(stage)
        return stage

    def fail(
        self,
        *,
        stage: str | None = None,
        error_code: str = "",
        message: str = "",
        retryable: bool | None = None,
    ) -> PipelineFailure:
        failed_stage = stage if stage in PIPELINE_STAGES else self.status
        code = error_code or DEFAULT_ERROR_CODES.get(failed_stage, "PIPELINE_FAILED")
        can_retry = code not in NON_RETRYABLE_CODES if retryable is None else bool(retryable)
        self.failure = PipelineFailure(
            status="failed",
            stage=failed_stage,
            error_code=code,
            retryable=can_retry,
            message=str(message or code),
        )
        return self.failure

    def fail_from_exception(self, exc: Exception) -> PipelineFailure:
        if isinstance(exc, PipelineStageError):
            return self.fail(
                stage=exc.stage,
                error_code=exc.error_code,
                retryable=exc.retryable,
                message=str(exc),
            )
        return self.fail(message=str(exc))

    def event(self, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pipeline": self.pipeline,
            "item_id": self.item_id,
            "status": "failed" if self.failure else self.status,
            "stage": self.failure.stage if self.failure else self.status,
            "history": list(self.history),
        }
        if self.failure:
            payload.update(self.failure.to_dict())
        payload.update(extra)
        return payload
