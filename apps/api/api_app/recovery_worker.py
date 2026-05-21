from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api_app.metadata_analysis_runs import (
    execute_metadata_analysis_run,
    metadata_analysis_run_stale_before,
)
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.metadata_design_runs import (
    execute_metadata_design_run,
    metadata_design_run_stale_before,
)
from api_app.metadata_design_service import MetadataDesignChatService
from api_app.repositories import WorkflowRepository
from api_app.workflow import WorkflowService

DEFAULT_METADATA_ANALYSIS_RUN_WORKER_INTERVAL_SECONDS = 10
DEFAULT_METADATA_ANALYSIS_RUN_WORKER_BATCH_SIZE = 5
DEFAULT_SP_WORKFLOW_STALE_SECONDS = 30 * 60
MIN_WORKER_INTERVAL_SECONDS = 1
MIN_WORKER_BATCH_SIZE = 1
MIN_SP_WORKFLOW_STALE_SECONDS = 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryWorkerReport:
    metadata_runs_claimed: int = 0
    metadata_design_runs_claimed: int = 0
    sp_jobs_recovered: int = 0
    sp_jobs_failed: int = 0
    errors: tuple[str, ...] = ()


def run_recovery_once(
    *,
    repository: WorkflowRepository,
    metadata_service: MetadataAnalysisService,
    metadata_design_service: MetadataDesignChatService | None = None,
    workflow_service: WorkflowService | None = None,
    batch_size: int | None = None,
) -> RecoveryWorkerReport:
    normalized_batch_size = metadata_analysis_run_worker_batch_size(batch_size)
    metadata_runs_claimed = 0
    metadata_design_runs_claimed = 0
    sp_jobs_recovered = 0
    sp_jobs_failed = 0
    errors: list[str] = []
    workflow = workflow_service or WorkflowService(repository)

    try:
        recoverable_runs = repository.list_recoverable_metadata_analysis_runs(
            stale_before=metadata_analysis_run_stale_before(),
            limit=normalized_batch_size,
        )
    except Exception as exc:  # noqa: BLE001 - worker logs sanitized blockers and continues
        errors.append(_safe_error_code(exc))
        recoverable_runs = []

    for record in recoverable_runs:
        try:
            claimed = execute_metadata_analysis_run(
                run_id=record.run_id,
                request=None,
                service=metadata_service,
                repository=repository,
            )
        except Exception as exc:  # noqa: BLE001 - next worker tick can retry active runs
            errors.append(_safe_error_code(exc))
            continue
        if claimed:
            metadata_runs_claimed += 1

    if metadata_design_service is not None:
        try:
            recoverable_design_runs = repository.list_recoverable_metadata_design_runs(
                stale_before=metadata_design_run_stale_before(),
                limit=normalized_batch_size,
            )
        except Exception as exc:  # noqa: BLE001 - worker logs sanitized blockers and continues
            errors.append(_safe_error_code(exc))
            recoverable_design_runs = []

        for record in recoverable_design_runs:
            try:
                claimed = execute_metadata_design_run(
                    run_id=record.run_id,
                    request=None,
                    service=metadata_design_service,
                    repository=repository,
                )
            except Exception as exc:  # noqa: BLE001 - next worker tick can retry active runs
                errors.append(_safe_error_code(exc))
                continue
            if claimed:
                metadata_design_runs_claimed += 1

    try:
        stale_jobs = repository.list_stale_active_jobs(
            stale_before=sp_workflow_stale_before(),
            limit=normalized_batch_size,
        )
    except Exception as exc:  # noqa: BLE001 - worker logs sanitized blockers and continues
        errors.append(_safe_error_code(exc))
        stale_jobs = []

    for job in stale_jobs:
        try:
            claimed = repository.claim_stale_active_job(
                job.job_id,
                stale_before=sp_workflow_stale_before(),
            )
            if claimed is None:
                continue
            recovered = workflow.resume_sp_workflow(claimed.job_id)
        except Exception as exc:  # noqa: BLE001 - keep worker alive for later ticks
            errors.append(_safe_error_code(exc))
            continue
        if recovered.status.value == "FAILED":
            sp_jobs_failed += 1
        else:
            sp_jobs_recovered += 1

    return RecoveryWorkerReport(
        metadata_runs_claimed=metadata_runs_claimed,
        metadata_design_runs_claimed=metadata_design_runs_claimed,
        sp_jobs_recovered=sp_jobs_recovered,
        sp_jobs_failed=sp_jobs_failed,
        errors=tuple(errors),
    )


async def recovery_worker_loop(
    *,
    repository_factory: Callable[[], WorkflowRepository],
    metadata_service_factory: Callable[[], MetadataAnalysisService],
    metadata_design_service_factory: Callable[[], MetadataDesignChatService] | None = None,
) -> None:
    interval_seconds = metadata_analysis_run_worker_interval_seconds()
    batch_size = metadata_analysis_run_worker_batch_size()
    while True:
        try:
            report = await asyncio.to_thread(
                _run_recovery_tick,
                repository_factory,
                metadata_service_factory,
                metadata_design_service_factory,
                batch_size,
            )
            if (
                report.metadata_runs_claimed
                or report.metadata_design_runs_claimed
                or report.sp_jobs_recovered
                or report.sp_jobs_failed
                or report.errors
            ):
                logger.info(
                    "Recovery worker tick completed metadataRunsClaimed=%s "
                    "metadataDesignRunsClaimed=%s spJobsRecovered=%s "
                    "spJobsFailed=%s errors=%s",
                    report.metadata_runs_claimed,
                    report.metadata_design_runs_claimed,
                    report.sp_jobs_recovered,
                    report.sp_jobs_failed,
                    list(report.errors),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - background worker must stay alive
            logger.warning("Recovery worker tick failed error=%s", _safe_error_code(exc))
        await asyncio.sleep(interval_seconds)


def metadata_analysis_run_worker_interval_seconds() -> int:
    return _env_int(
        "METADATA_ANALYSIS_RUN_WORKER_INTERVAL_SECONDS",
        DEFAULT_METADATA_ANALYSIS_RUN_WORKER_INTERVAL_SECONDS,
        minimum=MIN_WORKER_INTERVAL_SECONDS,
    )


def metadata_analysis_run_worker_batch_size(value: int | None = None) -> int:
    if value is None:
        value = _env_int(
            "METADATA_ANALYSIS_RUN_WORKER_BATCH_SIZE",
            DEFAULT_METADATA_ANALYSIS_RUN_WORKER_BATCH_SIZE,
            minimum=MIN_WORKER_BATCH_SIZE,
        )
    return max(min(int(value), 100), MIN_WORKER_BATCH_SIZE)


def sp_workflow_stale_seconds() -> int:
    return _env_int(
        "SP_WORKFLOW_STALE_SECONDS",
        DEFAULT_SP_WORKFLOW_STALE_SECONDS,
        minimum=MIN_SP_WORKFLOW_STALE_SECONDS,
    )


def sp_workflow_stale_before(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    return reference - timedelta(seconds=sp_workflow_stale_seconds())


def _run_recovery_tick(
    repository_factory: Callable[[], WorkflowRepository],
    metadata_service_factory: Callable[[], MetadataAnalysisService],
    metadata_design_service_factory: Callable[[], MetadataDesignChatService] | None,
    batch_size: int,
) -> RecoveryWorkerReport:
    repository = repository_factory()
    metadata_service = metadata_service_factory()
    metadata_design_service = (
        metadata_design_service_factory() if metadata_design_service_factory else None
    )
    return run_recovery_once(
        repository=repository,
        metadata_service=metadata_service,
        metadata_design_service=metadata_design_service,
        workflow_service=WorkflowService(repository),
        batch_size=batch_size,
    )


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(value, minimum)


def _safe_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return exc.__class__.__name__
