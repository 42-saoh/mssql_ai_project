from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from mssql_mcp_app.errors import MetadataToolError

from api_app.errors import code_for_status
from api_app.metadata_design_service import MetadataDesignChatService
from api_app.metadata_service import MetadataSearchDependencyError
from api_app.repositories import (
    MetadataDesignRunPersistenceError,
    MetadataDesignRunRecord,
    WorkflowRepository,
    prefixed_id,
)
from api_app.schemas import (
    MetadataDesignConversation,
    MetadataDesignResult,
    MetadataDesignRunError,
    MetadataDesignRunRequest,
    MetadataDesignRunStatus,
)

DEFAULT_METADATA_DESIGN_RUN_STALE_SECONDS = 30 * 60
MIN_METADATA_DESIGN_RUN_STALE_SECONDS = 60
TERMINAL_METADATA_DESIGN_RUN_STATUSES = frozenset({"SUCCEEDED", "FAILED"})
SECRET_LIKE_TEXT_RE = re.compile(
    (
        r"(password|secret|token|api[_-]?key|connection\s*string|row\s*data|"
        r"raw\s+(prompt|sql|provider)|full\s+(definition|sql)|"
        r"select\s+\*|drop\s+table|truncate\s+table|exec(?:ute)?\s+)"
    ),
    re.IGNORECASE,
)


def create_metadata_design_run(
    *,
    repository: WorkflowRepository,
    request: MetadataDesignRunRequest,
) -> MetadataDesignRunStatus:
    conversation_id = request.conversation_id or prefixed_id("metadata_design_conv")
    request_payload = _sanitize_design_request_payload(_model_payload(request))
    request_payload["conversationId"] = conversation_id
    record = repository.create_metadata_design_run(
        run_id=prefixed_id("metadata_design_run"),
        conversation_id=conversation_id,
        request=request_payload,
    )
    return present_metadata_design_run(record)


def get_metadata_design_run(
    *,
    repository: WorkflowRepository,
    run_id: str,
) -> MetadataDesignRunStatus | None:
    record = repository.get_metadata_design_run(run_id)
    return present_metadata_design_run(record) if record else None


def list_metadata_design_conversation(
    *,
    repository: WorkflowRepository,
    conversation_id: str,
    limit: int = 20,
) -> MetadataDesignConversation:
    records = repository.list_metadata_design_runs_for_conversation(
        conversation_id,
        limit=limit,
    )
    return MetadataDesignConversation(
        conversationId=conversation_id,
        runs=[present_metadata_design_run(record) for record in records],
    )


def execute_metadata_design_run(
    *,
    run_id: str,
    request: MetadataDesignRunRequest | None = None,
    service: MetadataDesignChatService,
    repository: WorkflowRepository,
) -> bool:
    claimed = repository.claim_metadata_design_run(
        run_id,
        stale_before=metadata_design_run_stale_before(),
    )
    if claimed is None:
        return False
    worker = MetadataDesignChatService(
        model_gateway=service.model_gateway,
        repository=repository,
    )
    try:
        design_request = request or MetadataDesignRunRequest.model_validate(claimed.request)
        if not design_request.conversation_id:
            design_request = design_request.model_copy(
                update={"conversation_id": claimed.conversation_id}
            )
        result = worker.design(design_request)
        if not _metadata_design_run_is_terminal(repository, run_id):
            repository.mark_metadata_design_run_succeeded(
                run_id,
                result=_model_payload(result),
            )
    except Exception as exc:  # noqa: BLE001 - polling exposes structured run failure
        error = _metadata_design_run_error(exc)
        try:
            if not _metadata_design_run_is_terminal(repository, run_id):
                repository.mark_metadata_design_run_failed(
                    run_id,
                    error=_model_payload(error),
                )
        except Exception:  # noqa: BLE001 - persistence outage leaves prior status intact
            return True
    return True


def present_metadata_design_run(
    record: MetadataDesignRunRecord,
) -> MetadataDesignRunStatus:
    result = (
        MetadataDesignResult.model_validate(record.result)
        if record.result is not None
        else None
    )
    error = (
        MetadataDesignRunError.model_validate(record.error)
        if record.error is not None
        else None
    )
    return MetadataDesignRunStatus(
        runId=record.run_id,
        conversationId=record.conversation_id,
        status=record.status,
        submittedAt=record.submitted_at,
        startedAt=record.started_at,
        completedAt=record.completed_at,
        request=MetadataDesignRunRequest.model_validate(record.request),
        result=result,
        error=error,
    )


def metadata_design_run_stale_seconds() -> int:
    raw_value = os.getenv("METADATA_DESIGN_RUN_STALE_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_METADATA_DESIGN_RUN_STALE_SECONDS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_METADATA_DESIGN_RUN_STALE_SECONDS
    return max(value, MIN_METADATA_DESIGN_RUN_STALE_SECONDS)


def metadata_design_run_stale_before(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    return reference - timedelta(seconds=metadata_design_run_stale_seconds())


def _metadata_design_run_error(exc: Exception) -> MetadataDesignRunError:
    if isinstance(exc, MetadataSearchDependencyError):
        return MetadataDesignRunError(
            code=exc.code,
            message=str(exc.detail),
            statusCode=exc.status_code,
        )
    if isinstance(exc, MetadataToolError):
        return MetadataDesignRunError(
            code=exc.code,
            message=exc.message,
            statusCode=exc.http_status,
        )
    if isinstance(exc, MetadataDesignRunPersistenceError):
        return MetadataDesignRunError(
            code=exc.code,
            message=str(exc),
            statusCode=exc.status_code,
        )
    if isinstance(exc, ValueError):
        return MetadataDesignRunError(
            code="VALIDATION_ERROR",
            message=str(exc),
            statusCode=422,
        )
    status_code = 500
    return MetadataDesignRunError(
        code=code_for_status(status_code),
        message="Metadata design run failed.",
        statusCode=status_code,
    )


def _model_payload(
    value: MetadataDesignRunRequest | MetadataDesignResult | MetadataDesignRunError,
) -> dict:
    return dict(value.model_dump(mode="json", by_alias=True))


def _sanitize_design_request_payload(value: dict[str, Any]) -> dict[str, Any]:
    def sanitize_text(text: str) -> str:
        return "[REDACTED_REVIEW_REQUIRED]" if SECRET_LIKE_TEXT_RE.search(text) else text

    def sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): sanitize(nested) for key, nested in item.items()}
        if isinstance(item, list):
            return [sanitize(nested) for nested in item]
        if isinstance(item, str):
            return sanitize_text(item)
        return item

    return dict(sanitize(value))


def _metadata_design_run_is_terminal(
    repository: WorkflowRepository,
    run_id: str,
) -> bool:
    record = repository.get_metadata_design_run(run_id)
    return bool(record and record.status in TERMINAL_METADATA_DESIGN_RUN_STATUSES)
