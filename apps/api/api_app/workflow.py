from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_analysis import (
    analyze_stored_procedure,
    build_context_packs,
    build_procedure_source_map,
    extract_statement_evidence,
    migration_guide_static_metrics,
)
from ai_agent_domain import ArtifactType, JobStatus, RequestedOutputType, WorkflowStepType
from ai_agent_generation import (
    GenerationContext,
    RenderedArtifact,
    RenderedBundle,
    build_migration_guide_payload,
    render_artifact,
)
from ai_agent_generation.models import GENERATOR_VERSION
from ai_agent_generation.utils import draft_quality_text
from ai_agent_runtime import (
    AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
    AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION,
    SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
    SP_OPERATION_PLANNER_PROMPT_VERSION,
    AgentRunPayload,
    AiDraftPackOrchestrator,
    AiGenerationFrameworkAdapter,
    ModelGateway,
    ModelGatewayError,
    ModelInvocationRecord,
    attach_planner_metrics_to_ai_tool_evidence,
    build_ai_java_mybatis_draft_pack_run,
    build_framework_runtime_from_env,
    build_model_gateway_from_env,
    build_semantic_analysis_run,
    build_sp_operation_model_run_result,
    validate_ai_java_mybatis_draft_pack_output,
    validate_sp_operation_model_output,
)
from ai_agent_runtime.ai_draft_pack import AiDraftPackValidationError
from ai_agent_runtime.gateway import model_profile_from_env
from ai_agent_runtime.models import (
    AI_DRAFT_PACK_MODEL_PROFILE_ID,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_VERSION,
    AgentRunStatus,
    stable_json_hash,
    text_hash,
)
from ai_agent_validation import (
    ValidationCheck,
    ValidationCheckResult,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
    validate_ai_java_mybatis_draft_pack_quality,
    validate_artifact,
)
from ai_agent_validation.ai_draft_pack import DEFAULT_REQUIRED_REVIEW_MARKERS
from mssql_mcp_app.metadata_discovery import source_database_for_profile

from api_app.ai_tool_orchestrator import AiToolOrchestrator
from api_app.backpressure import workflow_admission
from api_app.knowledge_service import persist_sp_workflow_knowledge
from api_app.metadata_gateway import McpMetadataGateway, MetadataCollectionResult, MetadataGateway
from api_app.platform_tool_orchestrator import PlatformToolOrchestrator
from api_app.repositories import (
    AgentRunRecord,
    ArtifactRecord,
    JobRecord,
    ValidationReportRecord,
    WorkflowRepository,
    WorkRequestRecord,
)
from api_app.schemas import SPAnalysisRequest
from api_app.target_keys import target_key_for_ref, target_key_for_target
from api_app.tracking import (
    IdempotencyConflictError,
    RequestTrackingContext,
    request_payload_hash,
)

WORKFLOW_METADATA_NOTE = (
    "근거 보강 필요: metadata는 MSSQL MCP registry 경계를 통해 수집되며 "
    "이 integration slice에서는 platform DB workflow repository에 저장됩니다."
)
DEPENDENCY_AGENT_TYPE = "LLM_SEMANTIC_ANALYST_DEPENDENCY"
OPERATION_MODEL_AGENT_TYPE = "LLM_SP_OPERATION_PLANNER"
SOURCE_DEPENDENCY_MODE_CONFIRMED = "CONFIRMED_PROCEDURES"
SP_WORKFLOW_RECOVERY_BLOCKED = "SP_WORKFLOW_RECOVERY_BLOCKED"
P41_OPERATION_MODEL_REVIEW_REQUIRED = "P41_OPERATION_MODEL_REVIEW_REQUIRED"
P42_AI_DRAFT_PACK_FAILED = "P42_AI_DRAFT_PACK_FAILED"
P42_AI_DRAFT_PACK_REVIEW_REQUIRED = "P42_AI_DRAFT_PACK_REVIEW_REQUIRED"
P42_INVENTORY_CONTRACT_INCOMPLETE = "P42_INVENTORY_CONTRACT_INCOMPLETE"
RECOVERABLE_SP_JOB_STATUSES = frozenset(
    {
        JobStatus.SUBMITTED,
        JobStatus.COLLECTING_METADATA,
        JobStatus.ANALYZING,
        JobStatus.GENERATING,
        JobStatus.VALIDATING,
    }
)
TERMINAL_SP_JOB_STATUSES = frozenset(
    {
        JobStatus.VALIDATION_COMPLETE,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.APPROVED,
        JobStatus.REJECTED,
        JobStatus.PUBLISHED,
    }
)


class WorkflowRecoveryBlocked(RuntimeError):
    code = SP_WORKFLOW_RECOVERY_BLOCKED

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AiDraftPackWorkflowError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DependencyProcedureCandidate:
    target_ref: str
    schema: str
    name: str
    depth: int
    database: str | None
    source_scope: str | None
    node: dict[str, Any]
    edge: dict[str, Any]
    evidence_refs: tuple[str, ...]


def dedupe_strings(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return tuple(deduped)


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository,
        metadata_gateway: MetadataGateway | None = None,
        model_gateway: ModelGateway | None = None,
        ai_generation_framework_adapter: AiGenerationFrameworkAdapter | None = None,
        ai_draft_pack_orchestrator: AiDraftPackOrchestrator | None = None,
    ) -> None:
        self.repository = repository
        self.metadata_gateway = metadata_gateway or McpMetadataGateway()
        self.model_gateway = model_gateway or build_model_gateway_from_env()
        if (
            ai_generation_framework_adapter is None
            and ai_draft_pack_orchestrator is None
        ):
            runtime = build_framework_runtime_from_env(model_gateway=self.model_gateway)
            ai_generation_framework_adapter = runtime.framework_adapter
            ai_draft_pack_orchestrator = runtime.ai_draft_pack_orchestrator
        self.ai_generation_framework_adapter = ai_generation_framework_adapter
        self.ai_draft_pack_orchestrator = ai_draft_pack_orchestrator
        self.ai_tool_orchestrator = AiToolOrchestrator(model_gateway=self.model_gateway)
        self.platform_tool_orchestrator = PlatformToolOrchestrator(
            model_gateway=self.model_gateway,
            repository=self.repository,
        )

    def submit_sp_analysis(
        self,
        request: SPAnalysisRequest,
        tracking: RequestTrackingContext | None = None,
        *,
        run_async: bool = False,
    ) -> tuple[WorkRequestRecord, JobRecord]:
        request_hash = request_payload_hash(request.to_response())
        tracking = (
            tracking or RequestTrackingContext(correlation_id="api-system")
        ).with_request_hash(request_hash)
        if tracking.idempotency_key:
            existing_request = self.repository.find_request_by_idempotency_key(
                tracking.idempotency_key
            )
            if existing_request is not None:
                if existing_request.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used for a different request payload."
                    )
                job = self.repository.find_job_by_request_id(existing_request.request_id)
                if job is None:
                    raise ValueError("Idempotent request exists without a workflow job.")
                self.repository.record_audit_event(
                    action="IDEMPOTENT_REQUEST_REPLAYED",
                    target_type="WORK_REQUEST",
                    target_ref_id=existing_request.request_id,
                    payload={"tracking": tracking.audit_payload()},
                    correlation_id=tracking.correlation_id,
                )
                existing_request.status = job.status
                return existing_request, job
        admission = workflow_admission() if not run_async else nullcontext()
        with admission:
            request_record, job = self.create_sp_analysis_job(request, tracking, request_hash)
            if not run_async:
                job = self.execute_submitted_sp_analysis(
                    job.job_id,
                    request_record=request_record,
                    acquire_admission=False,
                )
        request_record.status = job.status
        return request_record, job

    def create_sp_analysis_job(
        self,
        request: SPAnalysisRequest,
        tracking: RequestTrackingContext,
        request_hash: str | None = None,
    ) -> tuple[WorkRequestRecord, JobRecord]:
        request_hash = request_hash or request_payload_hash(request.to_response())
        target_key = target_key_for_target(
            request.db_profile_id,
            request.target.to_response(),
        )
        request_record = self.repository.create_request(
            db_profile_id=request.db_profile_id,
            target=request.target.to_response(),
            outputs=tuple(output.value for output in request.outputs),
            options=request.options.to_response(),
            request_hash=request_hash,
            correlation_id=tracking.correlation_id,
            idempotency_key=tracking.idempotency_key,
            target_key=target_key,
        )
        job = self.repository.create_job(
            request_record.request_id,
            correlation_id=tracking.correlation_id,
        )
        return request_record, job

    def execute_submitted_sp_analysis(
        self,
        job_id: str,
        request_record: WorkRequestRecord | None = None,
        *,
        acquire_admission: bool = True,
    ) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        request = request_record or self.repository.get_request(job.request_id)
        if request is None:
            return self.repository.fail_job(
                job_id,
                code=SP_WORKFLOW_RECOVERY_BLOCKED,
                message="SP workflow could not restore the original work request.",
            )
        try:
            return self.run_initial_workflow(
                job_id,
                request,
                acquire_admission=acquire_admission,
            )
        except Exception as exc:  # noqa: BLE001 - stored failure must stay sanitized
            return self.repository.fail_job(
                job_id,
                code=str(getattr(exc, "code", exc.__class__.__name__)),
                message=str(exc)[:2000],
            )

    def run_initial_workflow(
        self,
        job_id: str,
        request: WorkRequestRecord,
        *,
        acquire_admission: bool = True,
    ) -> JobRecord:
        if acquire_admission:
            with workflow_admission():
                return self.run_initial_workflow(
                    job_id,
                    request,
                    acquire_admission=False,
                )
        claimed = self.repository.claim_submitted_job(job_id)
        if claimed is None:
            current = self.repository.get_job(job_id)
            if current is None:
                raise KeyError(job_id)
            return current
        metadata = self._collect_metadata(job_id, request)
        self.repository.transition_job(
            job_id,
            status=JobStatus.ANALYZING,
            current_step=WorkflowStepType.ANALYZE,
        )
        definition_text = procedure_definition_text(metadata)
        static_analysis = static_analysis_payload(
            definition_text,
            source_name=f"{request.target['schema']}.{request.target['name']}",
            snapshot_id=metadata.snapshot_id,
        )
        metadata = metadata_with_static_dml_table_schemas(
            metadata,
            static_analysis=static_analysis,
            metadata_gateway=self.metadata_gateway,
        )
        orchestration = self.ai_tool_orchestrator.run(
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
        )
        metadata = orchestration.metadata
        platform_orchestration = self.platform_tool_orchestrator.run(
            job_id=job_id,
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
        )
        metadata = platform_orchestration.metadata
        tool_component_invocations = (
            *orchestration.component_invocations,
            *platform_orchestration.component_invocations,
        )
        agent_run = self._run_llm_semantic_analysis(
            job_id,
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
            tool_component_invocations=tool_component_invocations,
        )
        metadata = metadata_with_planner_metrics(
            metadata,
            agent_run=agent_run,
            ai_tool_component_invocations=orchestration.component_invocations,
            platform_tool_component_invocations=platform_orchestration.component_invocations,
        )
        operation_model_run = self._run_sp_operation_model_planning(
            job_id,
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
        )
        persist_sp_workflow_knowledge(
            repository=self.repository,
            job_id=job_id,
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
            agent_run=agent_run,
        )
        self.repository.save_metadata_collection(
            job_id=job_id,
            status=metadata.status,
            payload=sanitized_metadata_payload(metadata.as_dict()),
        )
        self.repository.transition_job(
            job_id,
            status=JobStatus.GENERATING,
            current_step=WorkflowStepType.GENERATE,
        )
        artifacts = self._generate_artifacts(
            job_id,
            request,
            metadata,
            agent_run,
            static_analysis=static_analysis,
            operation_model_run=operation_model_run,
        )

        self.repository.transition_job(
            job_id,
            status=JobStatus.VALIDATING,
            current_step=WorkflowStepType.VALIDATE,
        )
        reports = [self._validate_artifact_for_workflow(artifact) for artifact in artifacts]
        next_status = (
            JobStatus.FAILED
            if any(report.status == "FAILED" for report in reports)
            else JobStatus.VALIDATION_COMPLETE
        )
        return self.repository.transition_job(
            job_id,
            status=next_status,
            current_step=WorkflowStepType.VALIDATE,
        )

    def resume_sp_workflow(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status in TERMINAL_SP_JOB_STATUSES:
            return job
        if job.status not in RECOVERABLE_SP_JOB_STATUSES:
            return self.repository.fail_job(
                job_id,
                code=SP_WORKFLOW_RECOVERY_BLOCKED,
                message=f"SP workflow recovery does not support status {job.status.value}.",
            )
        request = self.repository.get_request(job.request_id)
        if request is None:
            return self.repository.fail_job(
                job_id,
                code=SP_WORKFLOW_RECOVERY_BLOCKED,
                message="SP workflow recovery could not restore the original work request.",
            )
        try:
            with workflow_admission():
                return self._resume_sp_workflow(job, request)
        except Exception as exc:  # noqa: BLE001 - recovery reports sanitized job failure
            return self.repository.fail_job(
                job_id,
                code=str(getattr(exc, "code", exc.__class__.__name__)),
                message=str(exc)[:2000],
            )

    def _resume_sp_workflow(
        self,
        job: JobRecord,
        request: WorkRequestRecord,
    ) -> JobRecord:
        metadata: MetadataCollectionResult | None = None
        static_analysis: dict[str, object] | None = None
        agent_run = self._existing_successful_root_agent_run(job.job_id)
        operation_model_run = self._existing_successful_operation_model_agent_run(job.job_id)
        if job.status in {
            JobStatus.SUBMITTED,
            JobStatus.COLLECTING_METADATA,
            JobStatus.ANALYZING,
            JobStatus.GENERATING,
        }:
            if job.status == JobStatus.SUBMITTED:
                self.repository.transition_job(
                    job.job_id,
                    status=JobStatus.COLLECTING_METADATA,
                    current_step=WorkflowStepType.COLLECT_METADATA,
                )
            elif job.status == JobStatus.COLLECTING_METADATA:
                self.repository.transition_job(
                    job.job_id,
                    status=JobStatus.COLLECTING_METADATA,
                    current_step=WorkflowStepType.COLLECT_METADATA,
                )
            metadata = self._collect_metadata(job.job_id, request)
            definition_text = procedure_definition_text(metadata)
            static_analysis = static_analysis_payload(
                definition_text,
                source_name=f"{request.target['schema']}.{request.target['name']}",
                snapshot_id=metadata.snapshot_id,
            )
            metadata = metadata_with_static_dml_table_schemas(
                metadata,
                static_analysis=static_analysis,
                metadata_gateway=self.metadata_gateway,
            )
            if job.status in {JobStatus.SUBMITTED, JobStatus.COLLECTING_METADATA}:
                self.repository.transition_job(
                    job.job_id,
                    status=JobStatus.ANALYZING,
                    current_step=WorkflowStepType.ANALYZE,
                )
            elif job.status == JobStatus.ANALYZING:
                self.repository.transition_job(
                    job.job_id,
                    status=JobStatus.ANALYZING,
                    current_step=WorkflowStepType.ANALYZE,
                )
            if agent_run is None:
                orchestration = self.ai_tool_orchestrator.run(
                    request_record=request,
                    metadata=metadata,
                    static_analysis=static_analysis,
                )
                metadata = orchestration.metadata
                platform_orchestration = self.platform_tool_orchestrator.run(
                    job_id=job.job_id,
                    request_record=request,
                    metadata=metadata,
                    static_analysis=static_analysis,
                )
                metadata = platform_orchestration.metadata
                agent_run = self._run_llm_semantic_analysis(
                    job.job_id,
                    request_record=request,
                    metadata=metadata,
                    static_analysis=static_analysis,
                    tool_component_invocations=(
                        *orchestration.component_invocations,
                        *platform_orchestration.component_invocations,
                    ),
                )
            metadata = metadata_with_planner_metrics(
                metadata,
                agent_run=agent_run,
                ai_tool_component_invocations=(),
                platform_tool_component_invocations=(),
            )
            if operation_model_run is None:
                operation_model_run = self._run_sp_operation_model_planning(
                    job.job_id,
                    request_record=request,
                    metadata=metadata,
                    static_analysis=static_analysis,
                )
            persist_sp_workflow_knowledge(
                repository=self.repository,
                job_id=job.job_id,
                request_record=request,
                metadata=metadata,
                static_analysis=static_analysis,
                agent_run=agent_run,
            )
            if self.repository.latest_metadata_for_job(job.job_id) is None:
                self.repository.save_metadata_collection(
                    job_id=job.job_id,
                    status=metadata.status,
                    payload=sanitized_metadata_payload(metadata.as_dict()),
                )

        if job.status != JobStatus.VALIDATING:
            self.repository.transition_job(
                job.job_id,
                status=JobStatus.GENERATING,
                current_step=WorkflowStepType.GENERATE,
            )
            if metadata is None:
                metadata = self._collect_metadata(job.job_id, request)
                definition_text = procedure_definition_text(metadata)
                static_analysis = static_analysis_payload(
                    definition_text,
                    source_name=f"{request.target['schema']}.{request.target['name']}",
                    snapshot_id=metadata.snapshot_id,
                )
                metadata = metadata_with_static_dml_table_schemas(
                    metadata,
                    static_analysis=static_analysis,
                    metadata_gateway=self.metadata_gateway,
                )
            if operation_model_run is None:
                operation_model_run = self._run_sp_operation_model_planning(
                    job.job_id,
                    request_record=request,
                    metadata=metadata,
                    static_analysis=static_analysis,
                )
            artifacts = self._generate_artifacts(
                job.job_id,
                request,
                metadata,
                agent_run,
                static_analysis=static_analysis,
                operation_model_run=operation_model_run,
            )
            if not artifacts:
                raise WorkflowRecoveryBlocked(
                    "SP workflow recovery could not produce or reuse draft artifacts."
                )
            self.repository.transition_job(
                job.job_id,
                status=JobStatus.VALIDATING,
                current_step=WorkflowStepType.VALIDATE,
            )
        else:
            artifacts = self.repository.list_job_artifacts(job.job_id) or []
            if not artifacts:
                raise WorkflowRecoveryBlocked(
                    "SP workflow recovery found VALIDATING status without artifacts."
                )

        reports = [self._validate_artifact_for_workflow(artifact) for artifact in artifacts]
        next_status = (
            JobStatus.FAILED
            if any(report.status == "FAILED" for report in reports)
            else JobStatus.VALIDATION_COMPLETE
        )
        return self.repository.transition_job(
            job.job_id,
            status=next_status,
            current_step=WorkflowStepType.VALIDATE,
        )

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        correlation_id: str | None = None,
        actor: str | None = None,
    ) -> ValidationReportRecord:
        artifact = self._require_artifact(artifact_id)
        report = validate_artifact(artifact.validation_payload(), artifact_id=artifact_id)
        return self.repository.save_validation_report(
            artifact_id=artifact_id,
            status=report.status.value,
            checks=[check.as_dict() for check in report.checks],
            missing_evidence=list(report.missing_evidence),
            manual_review_points=list(report.manual_review_points),
            correlation_id=correlation_id,
            actor=actor or "api-system",
        )

    def _validate_artifact_for_workflow(
        self,
        artifact: ArtifactRecord,
    ) -> ValidationReportRecord:
        existing = self.repository.latest_validation_for(artifact.artifact_id)
        if existing is not None:
            return existing
        return self.validate_artifact(artifact.artifact_id)

    def _collect_metadata(
        self,
        job_id: str,
        request: WorkRequestRecord,
    ) -> MetadataCollectionResult:
        target = request.target
        metadata = self.metadata_gateway.collect_procedure_metadata(
            db_profile_id=request.db_profile_id,
            schema=str(target["schema"]),
            procedure_name=str(target["name"]),
        )
        return metadata

    def _generate_artifacts(
        self,
        job_id: str,
        request: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        agent_run: AgentRunRecord | None = None,
        static_analysis: dict[str, object] | None = None,
        operation_model_run: AgentRunRecord | None = None,
    ) -> list[ArtifactRecord]:
        context = generation_context_from_request(
            request,
            metadata,
            agent_run,
            static_analysis=static_analysis,
            operation_model_run=operation_model_run,
        )
        artifacts: list[ArtifactRecord] = []
        for output in request.outputs:
            if output == RequestedOutputType.SP_ANALYSIS_DOCUMENT.value:
                artifacts.append(
                    self._store_rendered_artifact(
                        job_id,
                        render_artifact(
                            ArtifactType.SP_ANALYSIS_DOC,
                            context,
                        ),
                    )
                )
            elif output == RequestedOutputType.DEPENDENCY_REPORT.value:
                artifacts.append(
                    self._store_rendered_artifact(
                        job_id,
                        render_artifact(
                            ArtifactType.DEPENDENCY_REPORT,
                            context,
                        ),
                    )
                )
            elif output == RequestedOutputType.JAVA_MYBATIS_DRAFT.value:
                ai_draft_run, ai_draft_quality = self._run_ai_draft_pack_planning(
                    job_id,
                    request_record=request,
                    context=context,
                )
                context = generation_context_from_request(
                    request,
                    metadata,
                    agent_run,
                    static_analysis=static_analysis,
                    operation_model_run=operation_model_run,
                    ai_draft_pack_run=ai_draft_run,
                )
                artifacts.extend(
                    self._store_ai_draft_pack_artifacts(
                        job_id,
                        ai_draft_run,
                        quality_report=ai_draft_quality,
                    )
                )
            else:
                artifacts.extend(
                    self._store_contract_placeholder_artifact(
                        job_id,
                        artifact_type,
                        request,
                        metadata,
                        agent_run,
                    )
                    for artifact_type in artifact_types_for_requested_output(output)
                )
        return artifacts

    def _run_sp_operation_model_planning(
        self,
        job_id: str,
        *,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        static_analysis: dict[str, object] | None,
    ) -> AgentRunRecord | None:
        if not java_mybatis_output_requested(request_record):
            return None
        target_ref = operation_model_target_ref(request_record, metadata)
        definition_text = procedure_definition_text(metadata)
        evidence_payload: dict[str, Any] | None = None
        if not definition_text:
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="PROCEDURE_DEFINITION_UNAVAILABLE",
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason="PROCEDURE_DEFINITION_UNAVAILABLE",
                evidence_payload=None,
            )
        try:
            extraction = extract_statement_evidence(
                definition_text,
                target_ref=target_ref,
                source_name=target_ref,
            )
            evidence_payload = operation_model_evidence_summary(extraction.to_storage_dict())
        except Exception as exc:  # noqa: BLE001 - workflow keeps sanitized review fallback
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="STATEMENT_EVIDENCE_EXTRACTION_FAILED",
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason=f"STATEMENT_EVIDENCE_EXTRACTION_FAILED:{exc.__class__.__name__}",
                evidence_payload=None,
            )
        if not extraction.statement_evidence:
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="STATEMENT_EVIDENCE_EMPTY",
                evidence_refs=extraction.evidence_refs,
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason="STATEMENT_EVIDENCE_EMPTY",
                evidence_payload=evidence_payload,
            )
        if not bool(request_record.options.get("useLlmAnalysis", False)):
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="LLM_OPERATION_MODEL_DISABLED",
                evidence_refs=extraction.evidence_refs,
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason="LLM_OPERATION_MODEL_DISABLED",
                evidence_payload=evidence_payload,
            )
        try:
            run_result = build_sp_operation_model_run_result(
                target_ref=target_ref,
                statement_evidence=extraction.statement_evidence,
                model_gateway=self.model_gateway,
                profile_id=str(request_record.options.get("llmProfileId") or ""),
                allowed_evidence_refs=extraction.evidence_refs,
            )
            for sidecar_run in run_result.sidecar_runs:
                self._save_agent_run_payload(
                    job_id=job_id,
                    request_record=request_record,
                    run_payload=sidecar_run,
                )
            run_payload = run_result.final_run
            if evidence_payload:
                run_payload = _append_operation_model_evidence_component(
                    run_payload,
                    evidence_payload=evidence_payload,
                )
            return self._save_agent_run_payload(
                job_id=job_id,
                request_record=request_record,
                run_payload=run_payload,
            )
        except ModelGatewayError as exc:
            for sidecar_run in getattr(exc, "sidecar_runs", ()):
                self._save_agent_run_payload(
                    job_id=job_id,
                    request_record=request_record,
                    run_payload=sidecar_run,
                )
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="SP_OPERATION_MODEL_PLANNER_FAILED",
                evidence_refs=extraction.evidence_refs,
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason=f"SP_OPERATION_MODEL_PLANNER_FAILED:{exc.code}",
                evidence_payload=evidence_payload,
                failure_diagnostics={
                    "failureStage": str(
                        exc.provider_error.get("failureStage")
                        or "sp_operation_model_planner"
                    ),
                    "errorCode": exc.code,
                    "errorClass": exc.__class__.__name__,
                    "providerError": dict(exc.provider_error),
                },
            )
        except Exception as exc:  # noqa: BLE001 - operation planning must not fail the job
            payload = operation_model_review_required_payload(
                target_ref=target_ref,
                reason="SP_OPERATION_MODEL_PLANNER_FAILED",
                evidence_refs=extraction.evidence_refs,
            )
            return self._save_operation_model_run(
                job_id=job_id,
                request_record=request_record,
                payload=payload,
                target_ref=target_ref,
                reason=f"SP_OPERATION_MODEL_PLANNER_FAILED:{exc.__class__.__name__}",
                evidence_payload=evidence_payload,
                failure_diagnostics={
                    "failureStage": "sp_operation_model_planner",
                    "errorCode": "SP_OPERATION_MODEL_PLANNER_FAILED",
                    "errorClass": exc.__class__.__name__,
                },
            )

    def _save_operation_model_run(
        self,
        *,
        job_id: str,
        request_record: WorkRequestRecord,
        payload: dict[str, Any],
        target_ref: str,
        reason: str,
        evidence_payload: dict[str, Any] | None,
        failure_diagnostics: Mapping[str, Any] | None = None,
    ) -> AgentRunRecord:
        validated = validate_sp_operation_model_output(payload).to_storage_dict()
        model_invocation = operation_model_fallback_invocation(
            payload=validated,
            profile_id=str(request_record.options.get("llmProfileId") or ""),
            reason=reason,
            evidence_payload=evidence_payload,
            failure_diagnostics=failure_diagnostics,
        )
        return self.repository.save_agent_run(
            job_id=job_id,
            agent_type=OPERATION_MODEL_AGENT_TYPE,
            status=AgentRunStatus.SUCCEEDED.value,
            target_ref=target_ref,
            summary=f"SP operation model requires review before multi-DTO generation: {reason}.",
            structured_output=validated,
            model_invocation=model_invocation.to_storage_dict(),
            target_key=request_record.target_key,
        )

    def _save_agent_run_payload(
        self,
        *,
        job_id: str,
        request_record: WorkRequestRecord,
        run_payload: AgentRunPayload,
    ) -> AgentRunRecord:
        return self.repository.save_agent_run(
            job_id=job_id,
            agent_type=run_payload.agent_type,
            status=run_payload.status.value,
            target_ref=run_payload.target_ref,
            summary=run_payload.summary,
            structured_output=run_payload.structured_output,
            model_invocation=run_payload.model_invocation.to_storage_dict(),
            target_key=request_record.target_key,
        )

    def _run_llm_semantic_analysis(
        self,
        job_id: str,
        *,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        static_analysis: dict[str, object],
        tool_component_invocations: tuple[dict[str, object], ...] = (),
    ) -> AgentRunRecord | None:
        if not bool(request_record.options.get("useLlmAnalysis", False)):
            return None
        target = request_record.target
        object_ref = f"{target['schema']}.{target['name']}"
        definition_text = procedure_definition_text(metadata)
        source_context_packs = source_context_packs_for_request(
            definition_text,
            request_record=request_record,
            source_name=object_ref,
        )
        definition_for_model = (
            definition_text
            if source_context_packs
            else None
        )
        if (
            os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1"
            and bool(request_record.options.get("allowSpDefinitionToModel", False))
            and source_context_mode_for_options(request_record.options) == "RETRIEVED_SPANS"
            and os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1"
        ):
            raise ModelGatewayError(
                "LLM_ALLOW_SP_TEXT=1 is required before high-quality live source analysis.",
                code="LLM_SP_TEXT_NOT_ALLOWED",
            )
        try:
            run_payload = build_semantic_analysis_run(
                target_ref=object_ref,
                metadata=metadata.as_dict(),
                static_analysis=static_analysis,
                procedure_definition=definition_for_model,
                source_context_packs=source_context_packs,
                model_gateway=self.model_gateway,
                profile_id=str(request_record.options.get("llmProfileId") or ""),
            )
        except ModelGatewayError as exc:
            self._record_failed_llm_agent_run(
                job_id=job_id,
                target_ref=object_ref,
                profile_id=str(request_record.options.get("llmProfileId") or ""),
                error_code=exc.code,
                provider_error=exc.provider_error,
                target_key=request_record.target_key,
            )
            raise
        dependency_analysis = self._run_dependency_semantic_analyses(
            job_id=job_id,
            request_record=request_record,
            metadata=metadata,
        )
        if dependency_analysis["enabled"]:
            run_payload = _append_dependency_semantic_analysis(
                run_payload,
                dependency_analysis=dependency_analysis,
            )
        if tool_component_invocations or (
            metadata.ai_tool_evidence
            and metadata.ai_tool_evidence.get("reviewMarkers")
        ) or (
            metadata.platform_tool_evidence
            and metadata.platform_tool_evidence.get("reviewMarkers")
        ):
            run_payload = _append_ai_tool_components(
                run_payload,
                ai_tool_component_invocations=tool_component_invocations,
                metadata=metadata,
            )
        return self.repository.save_agent_run(
            job_id=job_id,
            agent_type=run_payload.agent_type,
            status=run_payload.status.value,
            target_ref=run_payload.target_ref,
            summary=run_payload.summary,
            structured_output=run_payload.structured_output,
            model_invocation=run_payload.model_invocation.to_storage_dict(),
            target_key=request_record.target_key,
        )

    def _run_dependency_semantic_analyses(
        self,
        *,
        job_id: str,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
    ) -> dict[str, Any]:
        mode = source_dependency_mode_for_options(request_record.options)
        summary: dict[str, Any] = {
            "enabled": mode == SOURCE_DEPENDENCY_MODE_CONFIRMED,
            "mode": mode,
            "requestedDepth": dependency_depth_from_env(),
            "maxTasks": dependency_task_limit_from_env(),
            "selectedCount": 0,
            "analyzedCount": 0,
            "skippedCount": 0,
            "childRunCount": 0,
            "reusedChildRunCount": 0,
            "analyzedTargets": [],
            "skippedTargets": [],
            "reviewMarkers": [],
        }
        if mode != SOURCE_DEPENDENCY_MODE_CONFIRMED:
            return summary
        dependency_evidence = metadata.dependency_evidence or {}
        candidates, skipped = dependency_procedure_candidates(
            dependency_evidence,
            max_depth=summary["requestedDepth"],
            max_tasks=summary["maxTasks"],
        )
        summary["selectedCount"] = len(candidates)
        summary["skippedTargets"] = skipped
        summary["skippedCount"] = len(skipped)
        summary["reviewMarkers"].extend(dependency_review_markers(skipped))
        for candidate in candidates:
            candidate_target_key = target_key_for_ref(
                db_profile_id=request_record.db_profile_id,
                database=candidate.database,
                object_type="PROCEDURE",
                target_ref=candidate.target_ref,
            )
            existing_child_run = self._existing_successful_dependency_agent_run(
                job_id,
                candidate.target_ref,
                target_key=candidate_target_key,
            )
            if existing_child_run is not None:
                summary["analyzedCount"] += 1
                summary["childRunCount"] += 1
                summary["reusedChildRunCount"] += 1
                summary["analyzedTargets"].append(
                    {
                        "targetRef": candidate.target_ref,
                        "targetKey": candidate_target_key,
                        "agentRunId": existing_child_run.agent_run_id,
                        "depth": candidate.depth,
                        "database": candidate.database,
                        "sourceScope": candidate.source_scope,
                        "evidenceRefs": list(candidate.evidence_refs),
                        "structuredOutput": existing_child_run.structured_output,
                        "sourceContextSummary": dict(
                            existing_child_run.model_invocation.get(
                                "sourceContextSummary",
                            )
                            or {}
                        ),
                        "reused": True,
                    }
                )
                continue
            payload = self.metadata_gateway.collect_procedure_definition(
                db_profile_id=request_record.db_profile_id,
                schema=candidate.schema,
                procedure_name=candidate.name,
                referenced_database=candidate.database,
            )
            definition_payload = dict(payload.get("data") or {}) if payload else {}
            definition_text = str(definition_payload.get("definition") or "")
            if not definition_text or not definition_payload.get("hasDefinitionAccess", True):
                skipped_item = {
                    "targetRef": candidate.target_ref,
                    "reason": "DEFINITION_UNAVAILABLE",
                    "depth": candidate.depth,
                    "database": candidate.database,
                    "sourceScope": candidate.source_scope,
                    "evidenceRefs": list(candidate.evidence_refs),
                }
                summary["skippedTargets"].append(skipped_item)
                summary["skippedCount"] += 1
                summary["reviewMarkers"].extend(dependency_review_markers([skipped_item]))
                continue
            child_static = static_analysis_payload(
                definition_text,
                source_name=candidate.target_ref,
                snapshot_id=metadata.snapshot_id,
            )
            child_context_packs = source_context_packs_for_options(
                definition_text,
                options=request_record.options,
                source_name=candidate.target_ref,
            )
            try:
                child_payload = build_semantic_analysis_run(
                    target_ref=candidate.target_ref,
                    metadata=dependency_child_metadata(
                        request_record=request_record,
                        metadata=metadata,
                        candidate=candidate,
                        definition_payload=definition_payload,
                        tool_payload=payload,
                    ),
                    static_analysis=child_static,
                    procedure_definition=definition_text if child_context_packs else None,
                    source_context_packs=child_context_packs,
                    model_gateway=self.model_gateway,
                    profile_id=str(request_record.options.get("llmProfileId") or ""),
                )
            except ModelGatewayError as exc:
                self._record_failed_llm_agent_run(
                    job_id=job_id,
                    target_ref=candidate.target_ref,
                    profile_id=str(request_record.options.get("llmProfileId") or ""),
                    error_code=exc.code,
                    provider_error=exc.provider_error,
                    agent_type=DEPENDENCY_AGENT_TYPE,
                    target_key=candidate_target_key,
                )
                skipped_item = {
                    "targetRef": candidate.target_ref,
                    "reason": "SEMANTIC_ANALYSIS_FAILED",
                    "depth": candidate.depth,
                    "database": candidate.database,
                    "sourceScope": candidate.source_scope,
                    "evidenceRefs": list(candidate.evidence_refs),
                    "errorCode": exc.code,
                }
                summary["skippedTargets"].append(skipped_item)
                summary["skippedCount"] += 1
                summary["reviewMarkers"].extend(dependency_review_markers([skipped_item]))
                continue
            child_run = self.repository.save_agent_run(
                job_id=job_id,
                agent_type=DEPENDENCY_AGENT_TYPE,
                status=child_payload.status.value,
                target_ref=child_payload.target_ref,
                summary=child_payload.summary,
                structured_output=child_payload.structured_output,
                model_invocation=child_payload.model_invocation.to_storage_dict(),
                target_key=candidate_target_key,
            )
            summary["analyzedCount"] += 1
            summary["childRunCount"] += 1
            summary["analyzedTargets"].append(
                {
                    "targetRef": candidate.target_ref,
                    "targetKey": candidate_target_key,
                    "agentRunId": child_run.agent_run_id,
                    "depth": candidate.depth,
                    "database": candidate.database,
                    "sourceScope": candidate.source_scope,
                    "evidenceRefs": list(candidate.evidence_refs),
                    "structuredOutput": child_payload.structured_output,
                    "sourceContextSummary": child_payload.model_invocation.to_storage_dict().get(
                        "sourceContextSummary",
                        {},
                    ),
                }
            )
        return summary

    def _record_failed_llm_agent_run(
        self,
        *,
        job_id: str,
        target_ref: str,
        profile_id: str,
        error_code: str,
        provider_error: dict[str, str] | None = None,
        agent_type: str = "LLM_SEMANTIC_ANALYST",
        target_key: str | None = None,
    ) -> None:
        profile = model_profile_from_env(profile_id)
        structured_output = {
            "businessRules": [],
            "modernizationPoints": [],
            "riskFlags": [],
            "reviewMarkers": [
                {
                    "code": "LLM_SEMANTIC_ANALYSIS_FAILED",
                    "message": f"LLM semantic analysis가 안전 코드 {error_code}로 실패했습니다.",
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": [],
                }
            ],
            "conversionGuidance": [],
            "migrationGuideInsights": [],
            "assumptions": [
                "semantic analysis 실패로 remote model output은 사용하지 않았습니다.",
            ],
        }
        failure_input = {
            "targetRef": target_ref,
            "modelProfileId": profile.profile_id,
            "errorCode": error_code,
        }
        component_invocation: dict[str, object] = {
            "stage": "semantic_analysis",
            "status": "FAILED",
            "errorCode": error_code,
        }
        if provider_error:
            component_invocation["providerError"] = dict(provider_error)
        invocation = ModelInvocationRecord(
            provider=str(getattr(self.model_gateway, "provider", "openai")),
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=PROMPT_VERSION,
            output_schema_version=OUTPUT_SCHEMA_VERSION,
            input_hash=stable_json_hash(failure_input),
            prompt_hash=text_hash(f"{PROMPT_VERSION}:{target_ref}:{error_code}"),
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.FAILED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=None,
            provider_request_id=None,
            error_code=error_code,
            error_message=None,
            component_invocations=(component_invocation,),
        )
        self.repository.save_agent_run(
            job_id=job_id,
            agent_type=agent_type,
            status=AgentRunStatus.FAILED.value,
            target_ref=target_ref,
            summary=f"LLM semantic analysis가 안전 코드 {error_code}로 실패했습니다.",
            structured_output=structured_output,
            model_invocation=invocation.to_storage_dict(),
            target_key=target_key,
        )

    def _existing_successful_root_agent_run(self, job_id: str) -> AgentRunRecord | None:
        runs = self.repository.list_agent_runs(job_id, limit=100)
        if not runs:
            return None
        for run in runs:
            if (
                run.agent_type == "LLM_SEMANTIC_ANALYST"
                and run.status == AgentRunStatus.SUCCEEDED.value
            ):
                return run
        return None

    def _existing_successful_operation_model_agent_run(
        self,
        job_id: str,
    ) -> AgentRunRecord | None:
        runs = self.repository.list_agent_runs(job_id, limit=100)
        if not runs:
            return None
        for run in runs:
            if (
                run.agent_type == OPERATION_MODEL_AGENT_TYPE
                and run.status == AgentRunStatus.SUCCEEDED.value
            ):
                return run
        return None

    def _existing_successful_dependency_agent_run(
        self,
        job_id: str,
        target_ref: str,
        *,
        target_key: str | None = None,
    ) -> AgentRunRecord | None:
        runs = self.repository.list_agent_runs(job_id, limit=100)
        if not runs:
            return None
        for run in runs:
            if (
                run.agent_type == DEPENDENCY_AGENT_TYPE
                and run.status == AgentRunStatus.SUCCEEDED.value
                and target_key
                and run.target_key == target_key
            ):
                return run
        for run in runs:
            if (
                run.agent_type == DEPENDENCY_AGENT_TYPE
                and run.status == AgentRunStatus.SUCCEEDED.value
                and run.target_ref == target_ref
            ):
                return run
        return None

    def _run_ai_draft_pack_planning(
        self,
        job_id: str,
        *,
        request_record: WorkRequestRecord,
        context: GenerationContext,
    ) -> tuple[AgentRunRecord, ValidationReport]:
        target_ref = ai_draft_pack_target_ref(context, request_record)
        operation_model_markers = {
            str(marker) for marker in context.operation_model.get("reviewMarkers", [])
        }
        if P41_OPERATION_MODEL_REVIEW_REQUIRED in operation_model_markers and bool(
            request_record.options.get("allowSpDefinitionToModel", False)
        ) and ai_draft_pack_requires_branch_evidence(context):
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                reason="AI_DRAFT_PACK_SAFE_CONTEXT_UNAVAILABLE:P41_OPERATION_MODEL_REVIEW_REQUIRED",
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                "AI Draft Pack planner needs branch-level operation evidence before drafting.",
            )
        if not bool(request_record.options.get("useLlmAnalysis", False)):
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                reason="LLM_AI_DRAFT_PACK_DISABLED",
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                "AI Draft Pack planner is disabled for JAVA_MYBATIS_DRAFT.",
            )
        sanitized_context = ai_draft_pack_context(context)
        expected_inventory = ai_draft_pack_expected_inventory(context)
        inventory_findings = ai_draft_pack_inventory_findings(
            context,
            expected_inventory,
        )
        if inventory_findings:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_INVENTORY_CONTRACT_INCOMPLETE,
                reason="AI_DRAFT_PACK_INVENTORY_CONTRACT_INCOMPLETE",
                failure_stage="inventory_contract",
                validation_findings=inventory_findings,
            )
            raise AiDraftPackWorkflowError(
                P42_INVENTORY_CONTRACT_INCOMPLETE,
                "AI Draft Pack inventory contract is incomplete for the operation model.",
            )
        quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
        allowed_refs = ai_draft_pack_allowed_evidence_refs(
            context=sanitized_context,
            expected_inventory=expected_inventory,
        )
        if not allowed_refs:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                reason="AI_DRAFT_PACK_SAFE_EVIDENCE_UNAVAILABLE",
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                "AI Draft Pack planner has no sanitized evidence refs.",
            )
        try:
            if self.ai_draft_pack_orchestrator is not None:
                run_payload = self.ai_draft_pack_orchestrator.build_run(
                    target_ref=target_ref,
                    sanitized_draft_context=sanitized_context,
                    expected_inventory=expected_inventory,
                    quality_gates=quality_gates,
                    model_gateway=self.model_gateway,
                    profile_id=ai_draft_pack_profile_id(request_record),
                    allowed_evidence_refs=allowed_refs,
                )
            else:
                run_payload = build_ai_java_mybatis_draft_pack_run(
                    target_ref=target_ref,
                    sanitized_draft_context=sanitized_context,
                    expected_inventory=expected_inventory,
                    quality_gates=quality_gates,
                    model_gateway=self.model_gateway,
                    profile_id=ai_draft_pack_profile_id(request_record),
                    allowed_evidence_refs=allowed_refs,
                    framework_adapter=self.ai_generation_framework_adapter,
                    run_file_inventory_stage=self.ai_generation_framework_adapter is not None,
                )
            quality_report = validate_ai_java_mybatis_draft_pack_quality(
                run_payload.structured_output,
            )
            if (
                quality_report.status != ValidationStatus.PASSED
                and self.ai_draft_pack_orchestrator is None
            ):
                failed_run_payload = run_payload
                run_payload, quality_report = self._repair_ai_draft_pack_quality(
                    target_ref=target_ref,
                    request_record=request_record,
                    sanitized_context=sanitized_context,
                    expected_inventory=expected_inventory,
                    quality_gates=quality_gates,
                    allowed_refs=allowed_refs,
                    failed_report=quality_report,
                )
                run_payload = merge_ai_draft_pack_repair_components(
                    failed_run_payload=failed_run_payload,
                    repaired_run_payload=run_payload,
                )
        except AttributeError as exc:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                reason="AI_DRAFT_PACK_PLANNER_UNAVAILABLE",
                failure_stage="planner_unavailable",
                error_class=exc.__class__.__name__,
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                "AI Draft Pack planner is unavailable.",
            ) from exc
        except ModelGatewayError as exc:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_FAILED,
                reason=f"AI_DRAFT_PACK_PLANNER_FAILED:{exc.code}",
                failure_stage=ai_draft_pack_gateway_failure_stage(
                    exc,
                    framework_adapter=self.ai_generation_framework_adapter,
                ),
                error_code=exc.code,
                error_class=exc.__class__.__name__,
                provider_error=exc.provider_error,
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_FAILED,
                "AI Draft Pack planner failed before producing valid artifacts.",
            ) from exc
        except AiDraftPackValidationError as exc:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_FAILED,
                reason="AI_DRAFT_PACK_PLANNER_FAILED:AiDraftPackValidationError",
                failure_stage=ai_draft_pack_validation_failure_stage(
                    exc.findings,
                    framework_adapter=self.ai_generation_framework_adapter,
                ),
                error_class=exc.__class__.__name__,
                validation_findings=exc.findings,
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_FAILED,
                "AI Draft Pack planner failed before producing valid artifacts.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - failure run must stay sanitized
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_FAILED,
                reason=f"AI_DRAFT_PACK_PLANNER_FAILED:{exc.__class__.__name__}",
                failure_stage="planner_exception",
                error_class=exc.__class__.__name__,
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_FAILED,
                "AI Draft Pack planner failed before producing valid artifacts.",
            ) from exc
        if quality_report.status != ValidationStatus.PASSED:
            self._save_ai_draft_pack_failure_run(
                job_id=job_id,
                request_record=request_record,
                target_ref=target_ref,
                code=P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                reason="AI_DRAFT_PACK_QUALITY_REVIEW_REQUIRED",
                quality_report=quality_report,
                failure_stage="quality_validation",
                validation_findings=ai_draft_pack_quality_findings(quality_report),
            )
            raise AiDraftPackWorkflowError(
                P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
                "AI Draft Pack quality gate requires review.",
            )
        record = self.repository.save_agent_run(
            job_id=job_id,
            agent_type=run_payload.agent_type,
            status=run_payload.status.value,
            target_ref=run_payload.target_ref,
            summary=run_payload.summary,
            structured_output=run_payload.structured_output,
            model_invocation=run_payload.model_invocation.to_storage_dict(),
            target_key=request_record.target_key,
        )
        return record, quality_report

    def _repair_ai_draft_pack_quality(
        self,
        *,
        target_ref: str,
        request_record: WorkRequestRecord,
        sanitized_context: Mapping[str, Any],
        expected_inventory: Sequence[Mapping[str, Any]],
        quality_gates: Mapping[str, Any],
        allowed_refs: Sequence[str],
        failed_report: ValidationReport,
    ) -> tuple[AgentRunPayload, ValidationReport]:
        repair_context = ai_draft_pack_quality_repair_context(failed_report)
        run_payload = build_ai_java_mybatis_draft_pack_run(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=self.model_gateway,
            profile_id=ai_draft_pack_profile_id(request_record),
            allowed_evidence_refs=allowed_refs,
            repair_context=repair_context,
            framework_adapter=self.ai_generation_framework_adapter,
        )
        return (
            run_payload,
            validate_ai_java_mybatis_draft_pack_quality(run_payload.structured_output),
        )

    def _save_ai_draft_pack_failure_run(
        self,
        *,
        job_id: str,
        request_record: WorkRequestRecord,
        target_ref: str,
        code: str,
        reason: str,
        quality_report: ValidationReport | None = None,
        failure_stage: str = "ai_draft_pack_workflow_gate",
        error_code: str | None = None,
        error_class: str | None = None,
        provider_error: Mapping[str, Any] | None = None,
        validation_findings: Sequence[str] | None = None,
    ) -> AgentRunRecord:
        profile = model_profile_from_env(ai_draft_pack_profile_id(request_record))
        checks = [
            {
                "ruleId": check.rule_id,
                "severity": check.severity.value,
                "result": check.result.value,
                "message": check.message[:500],
            }
            for check in (quality_report.failed_checks if quality_report else ())
        ]
        diagnostics = ai_draft_pack_failure_diagnostics(
            failure_stage=failure_stage,
            error_code=error_code or code,
            error_class=error_class,
            provider_error=provider_error,
            validation_findings=validation_findings,
            quality_report=quality_report,
        )
        structured_output = {
            "schemaVersion": AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION,
            "contractTarget": "AiJavaMyBatisDraftPack",
            "targetRef": target_ref,
            "sourcePolicy": "sanitized_facts_only",
            "productionReady": False,
            "status": "FAILED",
            "reviewMarkers": [
                {
                    "code": code,
                    "message": reason,
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": [],
                }
            ],
            "qualityGateFindings": checks,
            "failureDiagnostics": diagnostics,
            "assumptions": [
                "AI Draft Pack failure records do not store generated Java/XML content.",
            ],
        }
        failure_input = {
            "targetRef": target_ref,
            "reason": reason,
            "code": code,
        }
        invocation = ModelInvocationRecord(
            provider="workflow",
            model="deterministic-ai-draft-pack-gate",
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort="none",
            prompt_version=AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
            output_schema_version=AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
            input_hash=stable_json_hash(failure_input),
            prompt_hash=text_hash(f"{AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION}:{reason}"),
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.FAILED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id=None,
            component_invocations=(
                {
                    "component": "ai_draft_pack_workflow_gate",
                    "status": "FAILED",
                    "errorCode": code,
                    "reason": reason,
                    "failureStage": failure_stage,
                    "errorClass": error_class or "",
                    "failureDiagnostics": diagnostics,
                },
            ),
        )
        return self.repository.save_agent_run(
            job_id=job_id,
            agent_type=AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
            status=AgentRunStatus.FAILED.value,
            target_ref=target_ref,
            summary=f"AI Draft Pack generation stopped: {reason}.",
            structured_output=structured_output,
            model_invocation=invocation.to_storage_dict(),
            target_key=request_record.target_key,
        )

    def _store_rendered_artifact(
        self,
        job_id: str,
        rendered: RenderedArtifact,
    ) -> ArtifactRecord:
        artifact_type = ArtifactType(rendered.artifact_type_value)
        existing = self.repository.find_job_artifact_by_type(job_id, artifact_type)
        if existing is not None:
            return existing
        return self.repository.add_artifact(
            job_id=job_id,
            artifact_type=artifact_type,
            title=rendered.title,
            content=rendered.content,
            evidence_refs=[ref.as_dict() for ref in rendered.evidence_refs],
            generator_version=rendered.generator_version,
            registry_refs=tuple(rendered.registry_refs),
            assumptions=dedupe_strings(
                tuple(rendered.assumptions) + (WORKFLOW_METADATA_NOTE,)
            ),
            review_required=rendered.review_required,
            extra=dict(rendered.extra),
        )

    def _store_java_mybatis_bundle(
        self,
        job_id: str,
        bundle: RenderedBundle,
    ) -> list[ArtifactRecord]:
        assumptions = dedupe_strings(
            tuple(bundle.manifest.assumptions)
            + tuple(bundle.blockers)
            + (WORKFLOW_METADATA_NOTE,)
        )
        artifacts = []
        for file in bundle.files:
            existing = self._find_existing_java_bundle_artifact(job_id, file)
            if existing is not None:
                artifacts.append(existing)
                continue
            artifacts.append(
                self.repository.add_artifact(
                    job_id=job_id,
                    artifact_type=file.artifact_type,
                    title=file.path,
                    content=file.content,
                    evidence_refs=java_bundle_file_evidence_refs(bundle, file),
                    generator_version=bundle.manifest.generator_version,
                    registry_refs=tuple(bundle.manifest.registry_refs),
                    assumptions=assumptions,
                    review_required=True,
                    extra=java_bundle_file_extra(bundle, file),
                )
            )
        return artifacts

    def _find_existing_java_bundle_artifact(
        self,
        job_id: str,
        file: Any,
    ) -> ArtifactRecord | None:
        if file.artifact_type != ArtifactType.DTO_DRAFT:
            return self.repository.find_job_artifact_by_type(job_id, file.artifact_type)
        for artifact in self.repository.list_job_artifacts(job_id) or []:
            if artifact.type != ArtifactType.DTO_DRAFT:
                continue
            if artifact.extra.get("bundleFilePath") == file.path:
                return artifact
        return None

    def _store_ai_draft_pack_artifacts(
        self,
        job_id: str,
        ai_draft_pack_run: AgentRunRecord,
        *,
        quality_report: ValidationReport,
    ) -> list[ArtifactRecord]:
        pack = validate_ai_java_mybatis_draft_pack_output(
            ai_draft_pack_run.structured_output,
        )
        artifacts: list[ArtifactRecord] = []
        for file in pack.files:
            artifact_type = ArtifactType(file.artifact_type.value)
            existing = self._find_existing_ai_draft_pack_artifact(
                job_id,
                artifact_type=artifact_type,
                file_path=file.path,
            )
            if existing is not None:
                artifacts.append(existing)
                continue
            assumptions = dedupe_strings(
                (
                    *pack.assumptions,
                    *file.review_markers,
                    WORKFLOW_METADATA_NOTE,
                )
            )
            artifacts.append(
                self.repository.add_artifact(
                    job_id=job_id,
                    artifact_type=artifact_type,
                    title=file.path,
                    content=file.content,
                    evidence_refs=ai_draft_pack_file_evidence_refs(file),
                    generator_version=GENERATOR_VERSION,
                    registry_refs=(
                        AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
                        AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
                    ),
                    assumptions=assumptions,
                    review_required=True,
                    extra=ai_draft_pack_file_extra(
                        ai_draft_pack_run,
                        pack,
                        file,
                        quality_report=quality_report,
                    ),
                )
            )
        return artifacts

    def _find_existing_ai_draft_pack_artifact(
        self,
        job_id: str,
        *,
        artifact_type: ArtifactType,
        file_path: str,
    ) -> ArtifactRecord | None:
        if artifact_type != ArtifactType.DTO_DRAFT:
            return self.repository.find_job_artifact_by_type(job_id, artifact_type)
        for artifact in self.repository.list_job_artifacts(job_id) or []:
            if artifact.type != ArtifactType.DTO_DRAFT:
                continue
            if artifact.extra.get("bundleFilePath") == file_path:
                return artifact
        return None

    def _store_contract_placeholder_artifact(
        self,
        job_id: str,
        artifact_type: ArtifactType,
        request: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        agent_run: AgentRunRecord | None = None,
    ) -> ArtifactRecord:
        existing = self.repository.find_job_artifact_by_type(job_id, artifact_type)
        if existing is not None:
            return existing
        target = request.target
        object_ref = f"{target['schema']}.{target['name']}"
        metadata_lines = metadata_summary_lines(metadata)
        content = "\n".join(
            [
                f"# {artifact_type.value} 초안",
                "",
                "## input_interpretation",
                f"- dbProfileId: `{request.db_profile_id}`",
                f"- target: `{object_ref}`",
                "",
                "## evidence_summary",
                *metadata_lines,
                "",
                "## metadata_summary",
                *metadata_detail_lines(metadata),
                "",
                "## assumptions_and_todo",
                f"- {WORKFLOW_METADATA_NOTE}",
                (
                    "- 근거 보강 필요: 이 artifact type에 사용할 package-backed renderer가 "
                    "아직 없어 근거 caveat로 표시합니다."
                ),
                "",
                "## quality_summary",
                "- 이 초안은 수집된 메타데이터만 사용하며 실행 가능한 변경을 포함하지 않습니다.",
                "",
                "## evidence_map",
                *metadata_lines,
                "",
                "## known_caveats",
                "- package-backed renderer 연결 전까지 구조와 세부 항목은 제한적입니다.",
                "",
                "## next_evidence_to_collect",
                (
                    "- 전용 renderer가 요구하는 추가 metadata field와 deterministic analyzer "
                    "결과를 수집합니다."
                ),
                "",
                "## draft_readiness",
                "- status: evidence caveat",
                "",
            ]
        )
        return self.repository.add_artifact(
            job_id=job_id,
            artifact_type=artifact_type,
            title=f"{artifact_type.value} 초안",
            content=draft_quality_text(content),
            evidence_refs=list(metadata.evidence_refs)
            or [
                {
                    "type": "USER_INPUT",
                    "objectRef": object_ref,
                    "locator": "request.target",
                }
            ],
            generator_version=GENERATOR_VERSION,
            registry_refs=("registry:api_contract_placeholder@0.1.0",),
            assumptions=(WORKFLOW_METADATA_NOTE,),
            review_required=True,
            extra={
                "source": "api_contract_placeholder",
                "metadata": sanitized_metadata_payload(metadata.as_dict()),
                "llmTrace": llm_trace_summary(agent_run),
            },
        )

    def _require_artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self.repository.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        return artifact


def generation_context_from_request(
    request: WorkRequestRecord,
    metadata: MetadataCollectionResult | None = None,
    agent_run: AgentRunRecord | None = None,
    static_analysis: dict[str, object] | None = None,
    operation_model_run: AgentRunRecord | None = None,
    ai_draft_pack_run: AgentRunRecord | None = None,
) -> GenerationContext:
    target = request.target
    schema = str(target["schema"])
    name = str(target["name"])
    entity_name = pascal_case(name)
    sp_name = f"{schema}.{name}"
    table = metadata.primary_table if metadata else None
    table_name = (
        f"{table['schema']}.{table['tableName']}"
        if table and table.get("schema") and table.get("tableName")
        else "REVIEW_REQUIRED.UNKNOWN_TABLE"
    )
    columns = generation_columns(metadata) or [
        {
            "name": "REVIEW_REQUIRED_COLUMN",
            "dbType": "varchar(100)",
            "nullable": True,
            "description": "review-required column pending metadata enrichment",
        }
    ]
    input_params = generation_parameters(metadata)
    result_shape = [str(column["name"]) for column in columns]
    llm_analysis = agent_run.structured_output if agent_run else {}
    metadata_payload = sanitized_metadata_payload(metadata.as_dict()) if metadata else {}
    dependency_evidence = dependency_evidence_for_generation(metadata)
    ai_tool_evidence = ai_tool_evidence_for_generation(metadata)
    platform_tool_evidence = platform_tool_evidence_for_generation(metadata)
    operation_model = operation_model_for_generation(operation_model_run)
    entity_name = operation_model_entity_name(operation_model) or entity_name
    migration_guide = build_migration_guide_payload(
        target_ref=sp_name,
        db_profile_id=request.db_profile_id,
        metadata=metadata_payload,
        static_analysis=static_analysis or {},
        llm_analysis=llm_analysis,
        input_params=input_params,
        result_shape=result_shape,
        sample_id=request.request_id,
    )
    request_payload: dict[str, object] = {
        "systemCode": system_code(request.db_profile_id),
        "businessCodeLv1": "workflow",
        "businessCodeLv2": "draft",
        "entityName": entity_name,
        "resourceName": kebab_case(entity_name),
        "description": f"{sp_name} draft workflow output",
        "generationMode": "spRebuild",
        "tableName": table_name,
        "spName": sp_name,
        "columns": columns,
        "inputParams": input_params,
        "resultShape": result_shape,
        "pkColumns": [],
        "authorId": "AI",
        "llmAnalysis": llm_analysis,
        "llmTrace": llm_trace_summary(agent_run),
        "dependencyEvidence": dependency_evidence,
        "aiToolEvidence": ai_tool_evidence,
        "platformToolEvidence": platform_tool_evidence,
        "migrationGuide": migration_guide,
    }
    if operation_model:
        request_payload["operationModel"] = operation_model
        request_payload["operationModelTrace"] = llm_trace_summary(operation_model_run)
    ai_draft_pack = ai_draft_pack_for_generation(ai_draft_pack_run)
    if ai_draft_pack:
        request_payload["aiDraftPack"] = ai_draft_pack
        request_payload["aiDraftPackTrace"] = llm_trace_summary(ai_draft_pack_run)
    return GenerationContext.from_mapping(
        {
            "sampleId": request.request_id,
            "request": request_payload,
            "evidence": {
                "sources": generation_evidence_sources(
                    metadata,
                    sp_name,
                    agent_run,
                    operation_model_run=operation_model_run,
                ),
                "assumptions": generation_assumptions(
                    agent_run,
                    operation_model=operation_model,
                ),
            },
        }
    )


def java_mybatis_output_requested(request: WorkRequestRecord) -> bool:
    return RequestedOutputType.JAVA_MYBATIS_DRAFT.value in set(request.outputs)


def ai_draft_pack_profile_id(_request: WorkRequestRecord) -> str:
    return AI_DRAFT_PACK_MODEL_PROFILE_ID


def ai_draft_pack_target_ref(context: GenerationContext, request: WorkRequestRecord) -> str:
    operation_model = context.operation_model
    if operation_model.get("targetRef"):
        return str(operation_model["targetRef"])
    target = request.target
    return f"{target['schema']}.{target['name']}"


def ai_draft_pack_context(context: GenerationContext) -> dict[str, Any]:
    operation_model = context.operation_model
    statement_evidence = operation_model.get("statementEvidence")
    dto_blueprints = operation_model.get("dtoBlueprints")
    operations = operation_model.get("operations")
    return {
        "targetRef": operation_model.get("targetRef") or context.sp_name,
        "entityName": context.entity_name,
        "spName": context.sp_name,
        "inputParams": [item.__dict__ for item in context.input_params],
        "resultShape": list(context.result_shape),
        "evidenceRefs": [ref.object_ref for ref in context.evidence_refs if ref.object_ref],
        "allowedEvidenceRefs": [
            ref.object_ref for ref in context.evidence_refs if ref.object_ref
        ],
        "operationModelSummary": {
            "schemaVersion": operation_model.get("schemaVersion"),
            "operationCount": len(operations) if isinstance(operations, list) else 0,
            "statementEvidenceCount": (
                len(statement_evidence) if isinstance(statement_evidence, list) else 0
            ),
            "dtoBlueprintCount": len(dto_blueprints) if isinstance(dto_blueprints, list) else 0,
            "reviewMarkers": list(operation_model.get("reviewMarkers") or []),
        },
        "operations": _safe_prompt_items(operations),
        "dtoBlueprints": _safe_prompt_items(dto_blueprints),
        "statementEvidence": _safe_prompt_items(statement_evidence),
        "llmTrace": context.value("llmTrace", {}),
        "operationModelTrace": context.value("operationModelTrace", {}),
        "dependencyEvidenceSummary": _evidence_summary(context.value("dependencyEvidence", {})),
        "aiToolEvidenceSummary": _evidence_summary(context.value("aiToolEvidence", {})),
        "platformToolEvidenceSummary": _evidence_summary(
            context.value("platformToolEvidence", {})
        ),
    }


def ai_draft_pack_expected_inventory(context: GenerationContext) -> list[dict[str, Any]]:
    operation_model = context.operation_model
    dto_blueprints = operation_model.get("dtoBlueprints")
    if isinstance(dto_blueprints, list):
        inventory = [
            _inventory_item_from_dto_blueprint(item, operation_model)
            for item in dto_blueprints
            if isinstance(item, Mapping)
            and str(item.get("name") or "") != "OperationModelReviewRequired"
        ]
        if inventory:
            entity_name = operation_model_entity_name(operation_model) or context.entity_name
            operation_ids = _operation_ids_for_inventory(inventory)
            refs = _evidence_refs_for_inventory(inventory)
            dto_names = [item["className"] for item in inventory]
            inventory.extend(
                [
                    _non_dto_inventory_item(
                        artifact_type=ArtifactType.SERVICE_DRAFT.value,
                        path=f"service/{entity_name}Service.java",
                        role="SERVICE",
                        class_name=f"{entity_name}Service",
                        operation_ids=operation_ids,
                        references=dto_names,
                        evidence_refs=refs,
                    ),
                    _non_dto_inventory_item(
                        artifact_type=ArtifactType.MAPPER_INTERFACE.value,
                        path=f"mapper/{entity_name}Mapper.java",
                        role="MAPPER_INTERFACE",
                        class_name=f"{entity_name}Mapper",
                        operation_ids=operation_ids,
                        references=dto_names,
                        evidence_refs=refs,
                    ),
                    _non_dto_inventory_item(
                        artifact_type=ArtifactType.MAPPER_XML.value,
                        path=f"mapper/{entity_name}MapperSQL.xml",
                        role="MAPPER_XML",
                        class_name=f"{entity_name}MapperSQL",
                        operation_ids=operation_ids,
                        references=dto_names,
                        evidence_refs=refs,
                    ),
                ]
            )
            return inventory
    refs = [ref.object_ref for ref in context.evidence_refs if ref.object_ref] or [
        "metadata.ai_draft_pack.review_required"
    ]
    return [
        {
            "artifactType": "DTO_DRAFT",
            "path": f"dto/{context.entity_name}SearchCriteria.java",
            "role": "QUERY_DTO",
            "className": f"{context.entity_name}SearchCriteria",
            "operationIds": ["reviewDraft"],
            "dtoRole": "QUERY",
            "requiredFields": [param.name for param in context.input_params],
            "evidenceRefs": refs,
            "reviewMarkers": ["P42_AI_DRAFT_PACK_REVIEW_REQUIRED"],
        },
        {
            "artifactType": "DTO_DRAFT",
            "path": f"dto/{context.entity_name}SearchRow.java",
            "role": "RESULT_DTO",
            "className": f"{context.entity_name}SearchRow",
            "operationIds": ["reviewDraft"],
            "dtoRole": "RESULT",
            "requiredFields": list(context.result_shape),
            "evidenceRefs": refs,
            "reviewMarkers": ["P42_AI_DRAFT_PACK_REVIEW_REQUIRED"],
        },
        _non_dto_inventory_item(
            artifact_type="SERVICE_DRAFT",
            path=f"service/{context.entity_name}Service.java",
            role="SERVICE",
            class_name=f"{context.entity_name}Service",
            operation_ids=["reviewDraft"],
            references=[
                f"{context.entity_name}SearchCriteria",
                f"{context.entity_name}SearchRow",
            ],
            evidence_refs=refs,
        ),
        _non_dto_inventory_item(
            artifact_type="MAPPER_INTERFACE",
            path=f"mapper/{context.entity_name}Mapper.java",
            role="MAPPER_INTERFACE",
            class_name=f"{context.entity_name}Mapper",
            operation_ids=["reviewDraft"],
            references=[
                f"{context.entity_name}SearchCriteria",
                f"{context.entity_name}SearchRow",
            ],
            evidence_refs=refs,
        ),
        _non_dto_inventory_item(
            artifact_type="MAPPER_XML",
            path=f"mapper/{context.entity_name}MapperSQL.xml",
            role="MAPPER_XML",
            class_name=f"{context.entity_name}MapperSQL",
            operation_ids=["reviewDraft"],
            references=[
                f"{context.entity_name}SearchCriteria",
                f"{context.entity_name}SearchRow",
            ],
            evidence_refs=refs,
        ),
    ]


def ai_draft_pack_inventory_findings(
    context: GenerationContext,
    expected_inventory: Sequence[Mapping[str, Any]],
) -> list[str]:
    operation_model = context.operation_model
    if not isinstance(operation_model, Mapping):
        return []
    markers = {str(marker) for marker in operation_model.get("reviewMarkers", [])}
    if P41_OPERATION_MODEL_REVIEW_REQUIRED in markers:
        return []
    operations = [
        item
        for item in operation_model.get("operations", [])
        if isinstance(item, Mapping)
    ]
    statements = [
        item
        for item in operation_model.get("statementEvidence", [])
        if isinstance(item, Mapping)
    ]
    dto_blueprints = [
        item
        for item in operation_model.get("dtoBlueprints", [])
        if isinstance(item, Mapping)
        and str(item.get("name") or "") != "OperationModelReviewRequired"
    ]
    if not operations and not dto_blueprints:
        return []

    findings: list[str] = []
    branch_heavy = ai_draft_pack_requires_branch_evidence(context)
    if branch_heavy:
        branch_predicates = {
            str((operation.get("branchCondition") or {}).get("expression") or "").strip()
            for operation in operations
            if isinstance(operation.get("branchCondition"), Mapping)
        }
        branch_predicates.discard("")
        statement_operations = {
            str(statement.get("operation") or "").upper()
            for statement in statements
            if str(statement.get("operation") or "").strip()
        }
        dto_roles = {
            str(dto.get("role") or "").upper()
            for dto in dto_blueprints
            if str(dto.get("role") or "").strip()
        }
        if len(operations) < 4:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: branch-heavy SP operation model "
                f"has only {len(operations)} operations."
            )
        if len(statements) < 4:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: branch-heavy SP operation model "
                f"has only {len(statements)} statement evidence items."
            )
        if len(dto_blueprints) < 4:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: branch-heavy SP operation model "
                f"has only {len(dto_blueprints)} DTO blueprints."
            )
        if len(branch_predicates) < 2:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: branch-heavy SP operation model "
                "does not expose enough distinct branch predicates."
            )
        if not (statement_operations & {"SELECT", "INSERT", "UPDATE", "DELETE", "EXECUTE", "CALL"}):
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: statement evidence does not expose "
                "DML, result, or call operations for draft generation."
            )
        if not (dto_roles & {"QUERY", "RESULT", "COMMAND", "BATCH_ITEM", "CALL_REQUEST"}):
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: DTO blueprints do not expose "
                "query/result/command/batch/call responsibilities."
            )

    inventory_dtos = {
        str(item.get("className") or "")
        for item in expected_inventory
        if item.get("artifactType") == ArtifactType.DTO_DRAFT.value
    }
    missing_dtos = sorted(
        _safe_java_class_name(
            str(item.get("name") or ""),
            role=str(item.get("role") or ""),
            fallback_stem=operation_model_entity_name(operation_model) or "Draft",
        )
        for item in dto_blueprints
        if str(item.get("name") or "")
        and _safe_java_class_name(
            str(item.get("name") or ""),
            role=str(item.get("role") or ""),
            fallback_stem=operation_model_entity_name(operation_model) or "Draft",
        )
        not in inventory_dtos
    )
    if missing_dtos:
        findings.append(
            f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: dtoBlueprints missing from inventory: "
            f"{', '.join(missing_dtos[:12])}."
        )

    statement_ids = {
        str(item.get("statementId") or "")
        for item in statements
        if str(item.get("statementId") or "")
    }
    covered_statement_ids: set[str] = set()
    for operation in operations:
        covered_statement_ids.update(
            str(ref)
            for ref in operation.get("statementRefs", [])
            if str(ref).strip()
        )
    uncovered = sorted(statement_ids - covered_statement_ids)
    if uncovered:
        findings.append(
            f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: statement evidence not covered by "
            f"operation contracts: {', '.join(uncovered[:12])}."
        )

    dto_count = len(inventory_dtos)
    write_or_call_count = sum(
        1
        for item in statements
        if str(item.get("operation") or "").upper()
        in {"INSERT", "UPDATE", "DELETE", "MERGE", "EXECUTE", "CALL"}
    )
    complex_model = len(operations) > 1 or write_or_call_count > 1 or len(statement_ids) > 3
    if complex_model and dto_count <= 2:
        findings.append(
            f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: complex SP inventory collapsed to "
            f"{dto_count} DTO files."
        )

    inventory_roles = {
        str(item.get("dtoRole") or "").upper()
        for item in expected_inventory
        if item.get("artifactType") == ArtifactType.DTO_DRAFT.value
    }
    needs_command_like_dto = any(
        str(item.get("operation") or "").upper()
        in {"INSERT", "UPDATE", "DELETE", "MERGE", "EXECUTE", "CALL"}
        for item in statements
    )
    if needs_command_like_dto and not (
        inventory_roles & {"COMMAND", "BATCH_ITEM", "CALL_REQUEST"}
    ):
        findings.append(
            f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: write/call responsibilities need "
            "COMMAND, BATCH_ITEM, or CALL_REQUEST DTO roles."
        )

    operation_ids = _operation_ids_for_inventory(expected_inventory)
    non_dto_items = [
        item
        for item in expected_inventory
        if item.get("artifactType")
        in {
            ArtifactType.SERVICE_DRAFT.value,
            ArtifactType.MAPPER_INTERFACE.value,
            ArtifactType.MAPPER_XML.value,
        }
    ]
    for artifact_type in (
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    ):
        matches = [
            item
            for item in non_dto_items
            if item.get("artifactType") == artifact_type
        ]
        if len(matches) != 1:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: expected exactly one "
                f"{artifact_type} inventory item."
            )
            continue
        missing_methods = [
            method
            for method in operation_ids
            if method not in {str(ref) for ref in matches[0].get("operationIds", [])}
        ]
        if missing_methods:
            findings.append(
                f"{P42_INVENTORY_CONTRACT_INCOMPLETE}: {artifact_type} missing "
                f"operation ids: {', '.join(missing_methods[:12])}."
            )
    return findings


def ai_draft_pack_requires_branch_evidence(context: GenerationContext) -> bool:
    parameter_names = [
        str(param.name or "").lstrip("@").lower()
        for param in context.input_params
        if str(param.name or "").strip()
    ]
    if len(parameter_names) < 4:
        return False
    branch_tokens = (
        "crud",
        "flag",
        "gubun",
        "mode",
        "action",
        "kind",
        "type",
        "status",
        "svalue",
    )
    return any(
        any(token in parameter for token in branch_tokens)
        for parameter in parameter_names
    )


def ai_draft_pack_quality_gates(
    context: GenerationContext,
    expected_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    dto_classes = [
        str(item.get("className"))
        for item in expected_inventory
        if item.get("artifactType") == ArtifactType.DTO_DRAFT.value
    ]
    operation_ids = _operation_ids_for_inventory(expected_inventory)
    review_markers = list(
        dict.fromkeys(
            [
                *DEFAULT_REQUIRED_REVIEW_MARKERS,
                *operation_model_review_markers_for_draft(context.operation_model),
            ]
        )
    )
    return {
        "requiredDtoClasses": dto_classes,
        "requiredServiceMethods": operation_ids,
        "requiredMapperMethods": operation_ids,
        "requiredReviewMarkers": review_markers,
        "blockerPatterns": [
            "OperationModelReviewRequired",
            "P41_OPERATION_MODEL_REVIEW_REQUIRED",
        ],
        "blankContentIsBlocker": True,
        "dtoCollapseIsBlocker": True,
        "fallbackSkeletonPersistenceAllowedOnFailure": False,
    }


def ai_draft_pack_quality_repair_context(report: ValidationReport) -> dict[str, Any]:
    failed = [
        {
            "ruleId": check.rule_id,
            "severity": check.severity.value,
            "message": check.message[:300],
        }
        for check in report.failed_checks[:20]
    ]
    return {
        "failureStage": "deterministic_quality_validation",
        "errorCode": "AI_DRAFT_PACK_QUALITY_GATE_FAILED",
        "errorClass": "ValidationReport",
        "reason": "Deterministic P42 quality gate failed.",
        "failedCheckCount": len(report.failed_checks),
        "failedChecks": failed,
        "instruction": (
            "Repair the draft pack so all expected files, DTO references, mapper methods, "
            "and required REVIEW_REQUIRED markers pass deterministic validation."
        ),
    }


def merge_ai_draft_pack_repair_components(
    *,
    failed_run_payload: AgentRunPayload,
    repaired_run_payload: AgentRunPayload,
) -> AgentRunPayload:
    failed_components = tuple(failed_run_payload.model_invocation.component_invocations)
    if not failed_components:
        return repaired_run_payload
    merged_invocation = dataclass_replace(
        repaired_run_payload.model_invocation,
        component_invocations=(
            *failed_components,
            *repaired_run_payload.model_invocation.component_invocations,
        ),
    )
    return dataclass_replace(repaired_run_payload, model_invocation=merged_invocation)


def ai_draft_pack_quality_findings(report: ValidationReport) -> list[str]:
    return [
        f"{check.rule_id}:{check.message[:300]}"
        for check in report.failed_checks[:20]
    ]


def ai_draft_pack_failure_diagnostics(
    *,
    failure_stage: str,
    error_code: str,
    error_class: str | None,
    provider_error: Mapping[str, Any] | None,
    validation_findings: Sequence[str] | None,
    quality_report: ValidationReport | None,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "failureStage": str(failure_stage),
        "errorCode": str(error_code),
    }
    if error_class:
        diagnostics["errorClass"] = str(error_class)
    safe_provider_error = _safe_provider_error(provider_error or {})
    if safe_provider_error:
        diagnostics["providerError"] = safe_provider_error
    safe_findings = _safe_ai_draft_validation_findings(validation_findings or ())
    if safe_findings:
        diagnostics["validationFindingCount"] = len(validation_findings or ())
        diagnostics["validationFindings"] = safe_findings
    if quality_report is not None:
        diagnostics["qualityFailedCheckCount"] = len(quality_report.failed_checks)
        diagnostics["qualityFailedRuleIds"] = list(
            dict.fromkeys(check.rule_id for check in quality_report.failed_checks)
        )[:20]
    return diagnostics


def _safe_provider_error(provider_error: Mapping[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key in ("type", "code", "param", "message", "stage", "findingCount", "findings"):
        value = provider_error.get(key)
        if value is not None:
            safe[key] = str(value)[:300]
    return safe


def ai_draft_pack_gateway_failure_stage(
    exc: ModelGatewayError,
    *,
    framework_adapter: AiGenerationFrameworkAdapter | None,
) -> str:
    if framework_adapter is None or not str(exc.code).startswith("P43_FRAMEWORK"):
        return "model_gateway"
    stage = str(exc.provider_error.get("stage") or "").strip()
    if stage in {"file_inventory", "file_content", "repair"}:
        return f"{stage}_framework_trace"
    return "framework_adapter_trace"


def ai_draft_pack_validation_failure_stage(
    findings: Sequence[str],
    *,
    framework_adapter: AiGenerationFrameworkAdapter | None,
) -> str:
    if framework_adapter is None:
        return "schema_validation"
    for stage in ("file_inventory", "file_content", "repair"):
        if any(str(finding).startswith(f"{stage}:") for finding in findings):
            return f"{stage}_schema_validation"
    return "framework_adapter_schema_validation"


def _safe_ai_draft_validation_findings(findings: Sequence[str]) -> list[str]:
    safe: list[str] = []
    for finding in findings[:20]:
        text = str(finding)
        safe.append(text[:300])
    return safe


def ai_draft_pack_allowed_evidence_refs(
    *,
    context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    refs: list[str] = []
    refs.extend(str(ref) for ref in context.get("allowedEvidenceRefs", []) if str(ref).strip())
    refs.extend(str(ref) for ref in context.get("evidenceRefs", []) if str(ref).strip())
    for item in expected_inventory:
        refs.extend(str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip())
    return tuple(dict.fromkeys(refs))


def _safe_prompt_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _evidence_summary(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    refs = payload.get("evidenceRefs")
    markers = payload.get("reviewMarkers")
    return {
        "evidenceRefs": list(refs) if isinstance(refs, list) else [],
        "reviewMarkers": list(markers) if isinstance(markers, list) else [],
        "summary": payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {},
    }


def _inventory_item_from_dto_blueprint(
    item: Mapping[str, Any],
    operation_model: Mapping[str, Any],
) -> dict[str, Any]:
    role = str(item.get("role") or "REVIEW_REQUIRED").upper()
    dto_name = _safe_java_class_name(
        str(item.get("name") or ""),
        role=role,
        fallback_stem=operation_model_entity_name(operation_model) or "Draft",
    )
    role_map = {
        "QUERY": "QUERY_DTO",
        "RESULT": "RESULT_DTO",
        "COMMAND": "COMMAND_DTO",
        "BATCH_ITEM": "BATCH_ITEM_DTO",
        "CALL_REQUEST": "CALL_REQUEST_DTO",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED",
    }
    fields = item.get("fields") if isinstance(item.get("fields"), list) else []
    blueprint_required_fields = [
        _safe_java_field_name(str(field.get("name") or ""), index=index)
        for index, field in enumerate(fields, start=1)
        if isinstance(field, Mapping)
        and _safe_java_field_name(str(field.get("name") or ""), index=index)
    ]
    blueprint_required_fields = list(dict.fromkeys(blueprint_required_fields))
    if not blueprint_required_fields:
        blueprint_required_fields = [
            _safe_java_field_name(str(field.get("source") or ""), index=index)
            for index, field in enumerate(fields, start=1)
            if isinstance(field, Mapping)
            and _safe_java_field_name(str(field.get("source") or ""), index=index)
        ]
    raw_operation_ids = [
        str(ref) for ref in item.get("operationIds", []) if str(ref).strip()
    ]
    statement_required_fields = (
        _call_request_statement_fields(
            operation_model=operation_model,
            operation_ids=raw_operation_ids,
        )
        if role == "CALL_REQUEST"
        else []
    )
    required_fields = [
        field
        for field in dict.fromkeys([*statement_required_fields, *blueprint_required_fields])
        if field and field != "field"
    ] or [
        "reviewRequiredField"
    ]
    evidence_refs = [
        str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip()
    ] or ["metadata.ai_draft_pack.review_required"]
    return {
        "artifactType": ArtifactType.DTO_DRAFT.value,
        "path": f"dto/{dto_name}.java",
        "role": role_map.get(role, "COMMAND_DTO"),
        "className": dto_name,
        "operationIds": _draft_operation_ids_for_dto(
            dto_name=dto_name,
            role=role,
            raw_operation_ids=raw_operation_ids,
            operation_model=operation_model,
        ),
        "dtoRole": role,
        "requiredFields": required_fields,
        "evidenceRefs": evidence_refs,
        "reviewMarkers": [
            str(marker) for marker in item.get("reviewMarkers", []) if str(marker).strip()
        ],
    }


def _call_request_statement_fields(
    *,
    operation_model: Mapping[str, Any],
    operation_ids: Sequence[str],
) -> list[str]:
    statement_refs: set[str] = set()
    operation_id_set = {str(item) for item in operation_ids if str(item).strip()}
    for operation in operation_model.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        operation_id = str(operation.get("operationId") or "")
        if operation_id_set and operation_id not in operation_id_set:
            continue
        statement_refs.update(
            str(ref)
            for ref in operation.get("statementRefs", [])
            if str(ref).strip()
        )
    fields: list[str] = []
    for statement in operation_model.get("statementEvidence", []):
        if not isinstance(statement, Mapping):
            continue
        statement_id = str(statement.get("statementId") or "")
        if statement_refs and statement_id not in statement_refs:
            continue
        operation = str(statement.get("operation") or "").upper()
        if operation not in {"EXECUTE", "CALL"}:
            continue
        inputs = statement.get("inputs")
        if not isinstance(inputs, Sequence) or isinstance(inputs, str | bytes):
            continue
        for index, value in enumerate(inputs, start=1):
            field = _safe_java_field_name(str(value), index=index)
            if field and field != "field":
                fields.append(field)
    return list(dict.fromkeys(fields))


def _draft_operation_ids_for_dto(
    *,
    dto_name: str,
    role: str,
    raw_operation_ids: Sequence[str],
    operation_model: Mapping[str, Any],
) -> list[str]:
    raw_refs = list(dict.fromkeys(str(item) for item in raw_operation_ids if str(item).strip()))
    method_ids = [
        method_id
        for method_id in (
            _draft_method_id_from_operation_ref(operation_id) for operation_id in raw_refs
        )
        if method_id
    ]
    if role in {"QUERY", "RESULT"}:
        return method_ids or ["reviewDraft"]
    if role == "CALL_REQUEST":
        statement_methods = _statement_phase_method_ids(
            operation_model=operation_model,
            operation_ids=raw_refs,
            statement_operations={"EXECUTE", "CALL"},
        )
        return (
            statement_methods
            or [_lower_camel_class_stem(dto_name)]
            or method_ids
            or ["reviewDraft"]
        )
    if role == "BATCH_ITEM":
        stem = _class_stem(dto_name)
        method = stem if stem.lower().endswith("batch") else f"{stem}Batch"
        return [_lower_camel_from_words(method)] if method else method_ids or ["reviewDraft"]
    if role == "COMMAND":
        if len(raw_refs) == 1 and _operation_has_single_dto_blueprint(
            operation_id=raw_refs[0],
            operation_model=operation_model,
        ):
            return method_ids or ["reviewDraft"]
        return [_lower_camel_class_stem(dto_name)] or method_ids or ["reviewDraft"]
    return method_ids or [_lower_camel_class_stem(dto_name)] or ["reviewDraft"]


def _draft_method_id_from_operation_ref(operation_id: str) -> str:
    text = str(operation_id or "").strip()
    if not text:
        return ""
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", text) if part]
    if len(parts) > 1 and parts[0].lower() in {"op", "operation", "operations"}:
        parts = parts[1:]
    candidate = _lower_camel_from_words(" ".join(parts) if parts else text)
    if candidate and not re.match(r"[A-Za-z_]", candidate[0]):
        candidate = f"draft{candidate[:1].upper()}{candidate[1:]}"
    return candidate


def _operation_has_single_dto_blueprint(
    *,
    operation_id: str,
    operation_model: Mapping[str, Any],
) -> bool:
    for operation in operation_model.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        if str(operation.get("operationId") or "") != operation_id:
            continue
        refs = [
            str(ref)
            for ref in operation.get("dtoBlueprintRefs", [])
            if str(ref).strip()
        ]
        return len(refs) == 1
    return False


def _statement_phase_method_ids(
    *,
    operation_model: Mapping[str, Any],
    operation_ids: Sequence[str],
    statement_operations: set[str],
) -> list[str]:
    operations = [
        item
        for item in operation_model.get("operations", [])
        if isinstance(item, Mapping)
        and (not operation_ids or str(item.get("operationId") or "") in operation_ids)
    ]
    statement_refs: set[str] = set()
    for operation in operations:
        statement_refs.update(
            str(ref)
            for ref in operation.get("statementRefs", [])
            if str(ref).strip()
        )
    methods: list[str] = []
    for statement in operation_model.get("statementEvidence", []):
        if not isinstance(statement, Mapping):
            continue
        statement_id = str(statement.get("statementId") or "")
        if statement_refs and statement_id not in statement_refs:
            continue
        operation = str(statement.get("operation") or "").upper()
        if operation not in statement_operations:
            continue
        phase = str(statement.get("phase") or statement_id or "")
        method = _lower_camel_from_words(phase)
        if method:
            methods.append(method)
    return list(dict.fromkeys(methods))


def _lower_camel_class_stem(class_name: str) -> str:
    return _lower_camel_from_words(_class_stem(class_name))


def _class_stem(class_name: str) -> str:
    return operation_model_entity_stem(class_name) or class_name


def _lower_camel_from_words(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [
        part
        for part in re.split(r"[^0-9A-Za-z]+", re.sub(r"(?<!^)(?=[A-Z])", "_", text))
        if part
    ]
    if not parts:
        return text[:1].lower() + text[1:]
    first, *rest = parts
    return first[:1].lower() + first[1:] + "".join(
        part[:1].upper() + part[1:] for part in rest
    )


def operation_model_review_markers_for_draft(
    operation_model: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(operation_model, Mapping):
        return []
    markers: list[str] = []
    markers.extend(_review_markers_from_value(operation_model.get("reviewMarkers")))
    for operation in operation_model.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        markers.extend(_review_markers_from_value(operation.get("riskMarkers")))
        branch = operation.get("branchCondition")
        if isinstance(branch, Mapping):
            markers.extend(_review_markers_from_value(branch.get("reviewMarkers")))
    for dto in operation_model.get("dtoBlueprints", []):
        if isinstance(dto, Mapping):
            markers.extend(_review_markers_from_value(dto.get("reviewMarkers")))
    excluded = {
        P41_OPERATION_MODEL_REVIEW_REQUIRED,
        "SINGLE_DTO_COLLAPSE_REVIEW_REQUIRED",
    }
    return sorted(
        {
            marker
            for marker in markers
            if "REVIEW_REQUIRED" in marker and marker not in excluded
        }
    )


def _review_markers_from_value(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(item) for item in value if str(item).strip()]


def _operation_ids_for_inventory(inventory: Sequence[Mapping[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in inventory:
        ids.extend(str(ref) for ref in item.get("operationIds", []) if str(ref).strip())
    return list(dict.fromkeys(ids)) or ["reviewDraft"]


def _evidence_refs_for_inventory(inventory: Sequence[Mapping[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in inventory:
        refs.extend(str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip())
    return list(dict.fromkeys(refs)) or ["metadata.ai_draft_pack.review_required"]


def _non_dto_inventory_item(
    *,
    artifact_type: str,
    path: str,
    role: str,
    class_name: str,
    operation_ids: Sequence[str],
    references: Sequence[str],
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifactType": artifact_type,
        "path": path,
        "role": role,
        "className": class_name,
        "operationIds": list(operation_ids),
        "references": list(references),
        "evidenceRefs": list(evidence_refs),
        "reviewMarkers": ["REVIEW_REQUIRED_DRAFT_ONLY"],
    }


def operation_model_for_generation(
    operation_model_run: AgentRunRecord | None,
) -> dict[str, Any] | None:
    if operation_model_run is None:
        return None
    payload = operation_model_run.structured_output
    if not isinstance(payload, Mapping):
        return None
    return validate_sp_operation_model_output(payload).to_storage_dict()


def ai_draft_pack_for_generation(
    ai_draft_pack_run: AgentRunRecord | None,
) -> dict[str, Any] | None:
    if ai_draft_pack_run is None:
        return None
    payload = ai_draft_pack_run.structured_output
    if not isinstance(payload, Mapping):
        return None
    return validate_ai_java_mybatis_draft_pack_output(payload).to_storage_dict()


def operation_model_entity_name(operation_model: Mapping[str, Any] | None) -> str | None:
    if not operation_model:
        return None
    markers = {str(marker) for marker in operation_model.get("reviewMarkers", [])}
    if P41_OPERATION_MODEL_REVIEW_REQUIRED in markers:
        return None
    dto_blueprints = operation_model.get("dtoBlueprints")
    if not isinstance(dto_blueprints, list):
        return None
    preferred_roles = {"QUERY", "RESULT"}
    candidates = [
        item
        for item in dto_blueprints
        if isinstance(item, Mapping) and str(item.get("role") or "") in preferred_roles
    ] or [item for item in dto_blueprints if isinstance(item, Mapping)]
    for dto in candidates:
        dto_name = str(dto.get("name") or "")
        if dto_name == "OperationModelReviewRequired":
            continue
        stem = operation_model_entity_stem(dto_name)
        if stem:
            return _pascal_from_ascii_tokens(stem) or stem
    return None


def operation_model_entity_stem(dto_name: str) -> str | None:
    for suffix in (
        "SearchCriteria",
        "SearchRow",
        "Criteria",
        "Command",
        "BatchItem",
        "CallRequest",
        "CallResult",
        "Request",
        "Row",
    ):
        if dto_name.endswith(suffix) and len(dto_name) > len(suffix):
            return dto_name[: -len(suffix)]
    return dto_name or None


def _safe_java_class_name(raw_name: str, *, role: str, fallback_stem: str) -> str:
    suffix_by_role = {
        "QUERY": "SearchCriteria",
        "RESULT": "SearchRow",
        "COMMAND": "Command",
        "BATCH_ITEM": "BatchItem",
        "CALL_REQUEST": "CallRequest",
        "CALL_RESULT": "CallResult",
        "REVIEW_REQUIRED": "ReviewRequiredDto",
    }
    candidate = _pascal_from_ascii_tokens(raw_name)
    fallback = _pascal_from_ascii_tokens(fallback_stem) or "Draft"
    suffix = suffix_by_role.get(str(role or "").upper(), "Command")
    if not candidate:
        candidate = f"{fallback}{suffix}"
    if not re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", candidate):
        candidate = f"{fallback}{suffix}"
    if suffix and candidate == fallback:
        candidate = f"{candidate}{suffix}"
    return candidate


def _safe_java_field_name(raw_name: str, *, index: int) -> str:
    text = str(raw_name or "").lstrip("@")
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", text) if part]
    if not parts:
        return f"reviewRequiredField{index}"
    candidate = parts[0][:1].lower() + parts[0][1:] + "".join(
        part[:1].upper() + part[1:] for part in parts[1:]
    )
    if not re.match(r"^[A-Za-z_$]", candidate):
        candidate = f"field{candidate[:1].upper()}{candidate[1:]}"
    return candidate


def _pascal_from_ascii_tokens(value: str) -> str:
    parts = [
        part
        for part in re.split(
            r"[^0-9A-Za-z]+",
            re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value or "")),
        )
        if part
    ]
    if not parts:
        return ""
    candidate = "".join(part[:1].upper() + part[1:] for part in parts)
    if candidate and not re.match(r"^[A-Za-z_$]", candidate):
        candidate = f"Draft{candidate}"
    return candidate


def operation_model_target_ref(
    request: WorkRequestRecord,
    metadata: MetadataCollectionResult | None,
) -> str:
    if metadata and metadata.object_ref:
        return metadata.object_ref
    target = request.target
    return f"{target['schema']}.{target['name']}"


def operation_model_review_required_payload(
    *,
    target_ref: str,
    reason: str,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    refs = [str(ref) for ref in (evidence_refs or ()) if str(ref).strip()]
    refs = refs or ["metadata.operation_model.review_required"]
    markers = list(dict.fromkeys([P41_OPERATION_MODEL_REVIEW_REQUIRED, reason]))
    statement_target_ref = operation_model_review_statement_target_ref(target_ref)
    return {
        "schemaVersion": "SpOperationModel.v0.1",
        "contractTarget": "SpOperationModel",
        "targetRef": target_ref or "sp.operation.review_required",
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "operations": [
            {
                "operationId": "reviewRequiredOperation",
                "crudFlag": "REVIEW_REQUIRED",
                "title": "Operation model review required",
                "summary": "Workflow could not build a branch-level SP operation model.",
                "branchCondition": {
                    "expression": "REVIEW_REQUIRED",
                    "variables": [],
                    "evidenceRefs": refs,
                    "status": "REVIEW_REQUIRED",
                },
                "statementRefs": ["stmt.operation_model.review_required"],
                "dtoBlueprintRefs": ["OperationModelReviewRequired"],
                "stateTransitions": [],
                "riskMarkers": markers,
                "evidenceRefs": refs,
                "status": "REVIEW_REQUIRED",
            }
        ],
        "statementEvidence": [
            {
                "statementId": "stmt.operation_model.review_required",
                "operation": "VALIDATE",
                "targetRef": statement_target_ref,
                "phase": "review_required",
                "inputs": [],
                "outputs": [],
                "writes": [],
                "crossDatabase": False,
                "reviewMarkers": markers,
                "evidenceRefs": refs,
                "status": "REVIEW_REQUIRED",
            }
        ],
        "dtoBlueprints": [
            {
                "name": "OperationModelReviewRequired",
                "role": "REVIEW_REQUIRED",
                "operationIds": ["reviewRequiredOperation"],
                "fields": [
                    {
                        "name": "reviewRequired",
                        "dbType": "varchar(4000)",
                        "source": reason,
                        "required": False,
                        "evidenceRefs": refs,
                    }
                ],
                "evidenceRefs": refs,
                "reviewMarkers": markers,
            }
        ],
        "reviewMarkers": markers,
        "evidenceRefs": refs,
        "assumptions": [
            f"{reason}: branch-level DTO blueprint planning requires review.",
            "Fallback operation model prevents legacy single-DTO collapse for complex SP drafts.",
        ],
    }


def operation_model_review_statement_target_ref(target_ref: str) -> str:
    normalized = str(target_ref or "").upper()
    if any(keyword in normalized for keyword in ("SELECT", "UPDATE", "INSERT", "DELETE")):
        return "operation_model.review_required_target"
    return target_ref or "operation_model.review_required_target"


def operation_model_evidence_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    statements = payload.get("statementEvidence") if isinstance(payload, Mapping) else []
    statement_items = [item for item in statements if isinstance(item, Mapping)]
    return {
        "version": str(payload.get("version") or ""),
        "targetRef": str(payload.get("targetRef") or ""),
        "sourceMapVersion": str(payload.get("sourceMapVersion") or ""),
        "statementCount": len(statement_items),
        "operationTypes": sorted(
            {
                str(item.get("operation") or "")
                for item in statement_items
                if str(item.get("operation") or "")
            }
        ),
        "reviewMarkers": [str(item) for item in payload.get("reviewMarkers", []) if str(item)],
        "evidenceRefs": [str(item) for item in payload.get("evidenceRefs", []) if str(item)],
        "productionReady": False,
    }


def operation_model_fallback_invocation(
    *,
    payload: Mapping[str, Any],
    profile_id: str,
    reason: str,
    evidence_payload: Mapping[str, Any] | None,
    failure_diagnostics: Mapping[str, Any] | None = None,
) -> ModelInvocationRecord:
    profile = model_profile_from_env(profile_id)
    invocation_input = {
        "reason": reason,
        "targetRef": payload.get("targetRef"),
        "evidenceSummary": dict(evidence_payload or {}),
        "failureDiagnostics": dict(failure_diagnostics or {}),
    }
    component = {
        "component": "sp_operation_model_workflow_gate",
        "status": "REVIEW_REQUIRED",
        "reviewMarker": P41_OPERATION_MODEL_REVIEW_REQUIRED,
        "reason": reason,
        "evidenceSummary": dict(evidence_payload or {}),
    }
    if failure_diagnostics:
        component["failureDiagnostics"] = dict(failure_diagnostics)
    return ModelInvocationRecord(
        provider="workflow",
        model="deterministic-operation-model-fallback",
        model_profile_id=profile.profile_id,
        model_registry_ref=profile.registry_ref,
        reasoning_effort="none",
        prompt_version=SP_OPERATION_PLANNER_PROMPT_VERSION,
        output_schema_version=SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
        input_hash=stable_json_hash(invocation_input),
        prompt_hash=text_hash(f"{SP_OPERATION_PLANNER_PROMPT_VERSION}:{reason}"),
        output_hash=stable_json_hash(payload),
        status=AgentRunStatus.SUCCEEDED,
        structured_output=dict(payload),
        token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        latency_ms=0,
        provider_request_id=None,
        component_invocations=(component,),
    )


def _append_operation_model_evidence_component(
    run_payload: AgentRunPayload,
    *,
    evidence_payload: Mapping[str, Any],
) -> AgentRunPayload:
    invocation = dataclass_replace(
        run_payload.model_invocation,
        component_invocations=(
            *run_payload.model_invocation.component_invocations,
            {
                "component": "sp_statement_evidence_extractor",
                "status": "SUCCEEDED",
                "evidenceSummary": dict(evidence_payload),
            },
        ),
    )
    return dataclass_replace(run_payload, model_invocation=invocation)


def ai_draft_pack_file_extra(
    ai_draft_pack_run: AgentRunRecord,
    pack: Any,
    file: Any,
    *,
    quality_report: ValidationReport,
) -> dict[str, Any]:
    scores = dict(quality_report.metadata.get("scores") or {})
    quality_score = file.quality_score
    if quality_score is None:
        quality_score = min(
            float(scores.get("requiredDtoFileCoverage", 1.0)),
            float(scores.get("requiredServiceMethodCoverage", 1.0)),
            float(scores.get("requiredMapperMethodCoverage", 1.0)),
            float(scores.get("requiredReviewMarkerCoverage", 1.0)),
        )
    return {
        "requestedOutputType": RequestedOutputType.JAVA_MYBATIS_DRAFT.value,
        "source": "ai_java_mybatis_draft_pack",
        "bundleFilePath": file.path,
        "bundleRole": file.artifact_type.value,
        "aiDraftPackSchema": pack.schema_version,
        "aiDraftPackTargetRef": pack.target_ref,
        "aiDraftPackAgentRunId": ai_draft_pack_run.agent_run_id,
        "aiFileRole": file.role.value,
        "operationIds": list(file.operation_ids),
        "dtoRole": file.dto_role,
        "qualityScore": quality_score,
        "aiEvidenceRefs": list(file.evidence_refs),
        "reviewMarkers": list(file.review_markers),
    }


def ai_draft_pack_file_evidence_refs(file: Any) -> list[dict[str, Any]]:
    object_ref = ai_draft_pack_visible_object_ref(file)
    return [
        {
            "type": "TEMPLATE",
            "objectRef": object_ref,
            "locator": f"ai-draft-pack#{file.path}",
        }
    ]


def ai_draft_pack_visible_object_ref(file: Any) -> str:
    content = str(file.content)
    class_name = str(file.class_name)
    if class_name and class_name in content:
        return class_name
    for reference in file.references:
        ref = str(reference)
        if ref and ref in content:
            return ref
    for operation_id in file.operation_ids:
        operation = str(operation_id)
        if operation and operation in content:
            return operation
    if "REVIEW_REQUIRED" in content:
        return "REVIEW_REQUIRED"
    return java_bundle_file_evidence_object_ref(file)


def java_bundle_file_extra(bundle: RenderedBundle, file: Any) -> dict[str, Any]:
    manifest_extra = dict(bundle.manifest.extra)
    bundle_files = manifest_extra.get("bundleFiles")
    file_extra: dict[str, Any] = {}
    if isinstance(bundle_files, Mapping):
        metadata = bundle_files.get(file.path)
        if isinstance(metadata, Mapping):
            file_extra = dict(metadata)
    extra = {
        "requestedOutputType": bundle.requested_output_type,
        "source": "java_mybatis_evidence_reconstructed_bundle",
        "bundleFilePath": file.path,
        "bundleRole": file_extra.get("bundleRole") or file.artifact_type.value,
    }
    for key in (
        "operationModelSchema",
        "operationModelTargetRef",
        "operationIds",
        "dtoRole",
    ):
        if key in file_extra:
            extra[key] = file_extra[key]
    return extra


def java_bundle_file_evidence_refs(bundle: RenderedBundle, file: Any) -> list[dict[str, Any]]:
    refs = [
        ref.as_dict()
        for ref in bundle.manifest.evidence_refs
        if ref.object_ref and ref.object_ref in file.content
    ]
    if refs:
        return refs
    fallback_ref = java_bundle_file_evidence_object_ref(file)
    return [
        {
            "type": "GENERATION_EVIDENCE",
            "objectRef": fallback_ref,
            "locator": f"java-mybatis-bundle#{file.path}",
        }
    ]


def java_bundle_file_evidence_object_ref(file: Any) -> str:
    file_name = str(file.path).rsplit("/", 1)[-1]
    if file_name.endswith(".java"):
        return file_name[:-5]
    if file_name.endswith("MapperSQL.xml"):
        return file_name[: -len("SQL.xml")]
    if file_name.endswith(".xml"):
        return file_name[:-4]
    return "REVIEW_REQUIRED"


def validation_record_to_report(record: ValidationReportRecord) -> ValidationReport:
    checks = []
    for item in record.checks:
        severity = str(item.get("severity") or "ERROR").upper()
        result = str(item.get("result") or item.get("status") or "FAIL").upper()
        if result == "PASSED":
            result = "PASS"
        elif result == "FAILED":
            result = "FAIL"
        checks.append(
            ValidationCheck(
                rule_id=str(item.get("ruleId") or item.get("rule_id") or "unknown"),
                severity=ValidationSeverity(severity),
                result=ValidationCheckResult(result),
                message=str(item.get("message") or ""),
            )
        )
    return ValidationReport(
        artifact_id=record.artifact_id,
        status=ValidationStatus(record.status),
        checks=tuple(checks),
        missing_evidence=tuple(record.missing_evidence),
        manual_review_points=tuple(record.manual_review_points),
        metadata={
            "validationReportId": record.validation_report_id,
            "storageResult": record.storage_result,
        },
    )


def artifact_types_for_requested_output(output: str) -> tuple[ArtifactType, ...]:
    if output == RequestedOutputType.TABLE_COLUMN_METADATA.value:
        return (ArtifactType.METADATA_QUERY_RESULT,)
    raise ValueError(f"Unsupported requested output type: {output}")


def metadata_summary_lines(metadata: MetadataCollectionResult) -> list[str]:
    if metadata.evidence_refs:
        return [
            f"- MSSQL_METADATA: `{ref['objectRef']}` ({ref['locator']})"
            for ref in metadata.evidence_refs
        ]
    return [f"- USER_INPUT: `{metadata.object_ref}`"]


def sanitized_metadata_payload(payload: dict[str, object]) -> dict[str, object]:
    sanitized = dict(payload)
    definition = sanitized.get("procedureDefinition")
    if isinstance(definition, dict):
        sanitized_definition = dict(definition)
        sanitized_definition.pop("definition", None)
        sanitized["procedureDefinition"] = sanitized_definition
    sanitized["dependencyEvidence"] = dependency_evidence_for_generation_payload(
        sanitized.get("dependencyEvidence")
    )
    sanitized["aiToolEvidence"] = ai_tool_evidence_for_generation_payload(
        sanitized.get("aiToolEvidence")
    )
    sanitized["platformToolEvidence"] = ai_tool_evidence_for_generation_payload(
        sanitized.get("platformToolEvidence")
    )
    return sanitized


def metadata_with_planner_metrics(
    metadata: MetadataCollectionResult,
    *,
    agent_run: AgentRunRecord | None,
    ai_tool_component_invocations: tuple[dict[str, object], ...],
    platform_tool_component_invocations: tuple[dict[str, object], ...] = (),
) -> MetadataCollectionResult:
    updated = metadata
    if isinstance(metadata.ai_tool_evidence, dict):
        evidence = attach_planner_metrics_to_ai_tool_evidence(
            metadata.ai_tool_evidence,
            deterministic_facts=_deterministic_facts_with_prefix(metadata, ("mcp.",)),
            component_invocations=ai_tool_component_invocations,
            structured_output=agent_run.structured_output if agent_run else None,
        )
        updated = dataclass_replace(updated, ai_tool_evidence=evidence)
    if isinstance(metadata.platform_tool_evidence, dict):
        evidence = attach_planner_metrics_to_ai_tool_evidence(
            metadata.platform_tool_evidence,
            deterministic_facts=_deterministic_facts_with_prefix(metadata, ("platform.",)),
            component_invocations=platform_tool_component_invocations,
            structured_output=agent_run.structured_output if agent_run else None,
        )
        updated = dataclass_replace(updated, platform_tool_evidence=evidence)
    return updated


def _deterministic_facts_with_prefix(
    metadata: MetadataCollectionResult,
    prefixes: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        fact
        for fact in metadata.deterministic_facts
        if any(str(fact.get("id") or "").startswith(prefix) for prefix in prefixes)
    )


def metadata_with_static_dml_table_schemas(
    metadata: MetadataCollectionResult,
    *,
    static_analysis: Mapping[str, Any] | None,
    metadata_gateway: object,
) -> MetadataCollectionResult:
    collect_table_schema = getattr(metadata_gateway, "collect_table_schema", None)
    if not callable(collect_table_schema):
        return metadata

    existing_keys = {
        _table_schema_key(table)
        for table in metadata.table_schemas
        if _table_schema_key(table)
    }
    table_schemas = list(metadata.table_schemas)
    for target in _static_dml_table_schema_targets(
        static_analysis,
        db_profile_id=metadata.db_profile_id,
    ):
        key = _table_schema_key(target)
        if not key or key in existing_keys:
            continue
        try:
            payload = collect_table_schema(
                db_profile_id=metadata.db_profile_id,
                schema=target["schema"],
                table_name=target["tableName"],
            )
        except Exception:
            continue
        table_schema = _table_schema_data(payload)
        if table_schema is None:
            continue
        table_schemas.append(table_schema)
        existing_keys.add(key)

    if len(table_schemas) == len(metadata.table_schemas):
        return metadata
    return dataclass_replace(
        metadata,
        table_schemas=tuple(table_schemas),
        notes=tuple(
            dedupe_strings(
                (
                    *metadata.notes,
                    "Static DML table schema metadata enriched through read-only get_table_schema.",
                )
            )
        ),
    )


def _static_dml_table_schema_targets(
    static_analysis: Mapping[str, Any] | None,
    *,
    db_profile_id: str,
) -> tuple[dict[str, str], ...]:
    if not isinstance(static_analysis, Mapping):
        return ()
    source_database = source_database_for_profile(db_profile_id)
    metrics = static_analysis.get("migrationGuideStaticMetrics")
    dml_operations = metrics.get("dmlOperations") if isinstance(metrics, Mapping) else ()
    if not isinstance(dml_operations, Sequence) or isinstance(dml_operations, str | bytes):
        return ()
    targets: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in dml_operations:
        if not isinstance(item, Mapping):
            continue
        parts = _sql_identifier_parts(str(item.get("targetRef") or ""))
        if len(parts) < 2 or parts[-1].startswith("#"):
            continue
        database = parts[-3] if len(parts) >= 3 else None
        if database and not _same_text(database, source_database):
            continue
        target = {"schema": parts[-2], "tableName": parts[-1]}
        key = _table_schema_key(target)
        if not key or key in seen:
            continue
        seen.add(key)
        targets.append(target)
    return tuple(targets)


def _table_schema_data(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
    if not isinstance(data, Mapping):
        return None
    schema = str(data.get("schema") or "").strip()
    table_name = str(data.get("tableName") or data.get("name") or "").strip()
    if not schema or not table_name:
        return None
    return dict(data)


def _table_schema_key(table: Mapping[str, Any]) -> tuple[str, str] | None:
    schema = str(table.get("schema") or "").strip()
    table_name = str(table.get("tableName") or table.get("name") or "").strip()
    if not schema or not table_name:
        return None
    return (schema.casefold(), table_name.casefold())


def _sql_identifier_parts(value: str) -> list[str]:
    return [
        _strip_sql_identifier_part(part)
        for part in str(value).strip().split(".")
        if _strip_sql_identifier_part(part)
    ]


def _strip_sql_identifier_part(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return stripped


def metadata_detail_lines(metadata: MetadataCollectionResult) -> list[str]:
    if not metadata.table_schemas:
        return ["- 근거 보강 필요: table schema metadata를 사용할 수 없습니다."]
    lines: list[str] = []
    for table in metadata.table_schemas:
        table_ref = f"{table.get('schema')}.{table.get('tableName')}"
        lines.append(f"- 테이블: `{table_ref}`")
        for column in table.get("columns", []):
            description = str(column.get("description", "")).strip()
            logical_name = str(column.get("logicalName", "")).strip()
            data_type = str(column.get("dataType", "")).strip()
            nullable = str(column.get("isNullable", True)).lower()
            label = f"{logical_name} - {description}" if logical_name else description
            lines.append(
                f"  - `{column.get('name')}` {data_type} nullable={nullable}: {label}"
            )
    return lines


def generation_columns(metadata: MetadataCollectionResult | None) -> list[dict[str, object]]:
    table = metadata.primary_table if metadata else None
    if not table:
        return []
    return [
        {
            "name": str(column.get("name", "")),
            "dbType": str(column.get("dataType", "")),
            "nullable": bool(column.get("isNullable", True)),
            "description": str(column.get("description", "")),
        }
        for column in table.get("columns", [])
        if column.get("name")
    ]


def generation_parameters(metadata: MetadataCollectionResult | None) -> list[dict[str, object]]:
    if not metadata or not metadata.procedure_parameters:
        return []
    return [
        {
            "name": str(parameter.get("name", "")).lstrip("@"),
            "dbType": str(parameter.get("dataType", "")),
            "required": not bool(parameter.get("hasDefault", False)),
        }
        for parameter in metadata.procedure_parameters.get("parameters", [])
        if parameter.get("name")
    ]


def generation_evidence_sources(
    metadata: MetadataCollectionResult | None,
    sp_name: str,
    agent_run: AgentRunRecord | None = None,
    operation_model_run: AgentRunRecord | None = None,
) -> list[dict[str, str | None]]:
    if not metadata:
        sources: list[dict[str, str | None]] = [
            {
                "type": "storedProcedure",
                "name": sp_name,
                "reason": "request target만 있으며 metadata collection을 사용할 수 없습니다.",
            }
        ]
    else:
        sources = [
            {
                "type": "storedProcedure",
                "name": sp_name,
                "reason": metadata.status,
                "locator": "MSSQL MCP procedure metadata",
                "snapshotId": metadata.snapshot_id,
            }
        ]
        sources.extend(
            {
                "type": "table",
                "name": f"{table['schema']}.{table['tableName']}",
                "reason": "MSSQL MCP table schema metadata 근거입니다.",
                "locator": "MSSQL MCP table schema metadata",
                "snapshotId": metadata.snapshot_id,
            }
            for table in metadata.table_schemas
            if table.get("schema") and table.get("tableName")
        )
        dependency_evidence = dependency_evidence_for_generation(metadata)
        sources.extend(
            {
                "type": "dependencyEvidence",
                "name": str(ref.get("objectRef") or metadata.object_ref),
                "reason": "MSSQL MCP dependency closure 근거입니다.",
                "locator": str(ref.get("locator") or "MSSQL MCP dependency closure"),
                "snapshotId": str(ref.get("snapshotId") or metadata.snapshot_id or ""),
            }
            for ref in dependency_evidence.get("evidenceRefs", [])
            if isinstance(ref, dict)
        )
    if agent_run:
        invocation = agent_run.model_invocation
        output_hash = str(invocation.get("outputHash") or "")
        sources.append(
            {
                "type": "llmInference",
                "name": output_hash or agent_run.target_ref,
                "reason": output_hash or agent_run.summary,
                "locator": "agent-runtime.modelInvocation.outputHash",
                "snapshotId": None,
            }
        )
    return sources


def dependency_evidence_for_generation(
    metadata: MetadataCollectionResult | None,
) -> dict[str, object]:
    if metadata is None:
        return {}
    return dependency_evidence_for_generation_payload(metadata.dependency_evidence)


def ai_tool_evidence_for_generation(
    metadata: MetadataCollectionResult | None,
) -> dict[str, object]:
    if metadata is None:
        return {}
    return ai_tool_evidence_for_generation_payload(metadata.ai_tool_evidence)


def platform_tool_evidence_for_generation(
    metadata: MetadataCollectionResult | None,
) -> dict[str, object]:
    if metadata is None:
        return {}
    return ai_tool_evidence_for_generation_payload(metadata.platform_tool_evidence)


def ai_tool_evidence_for_generation_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        "status": str(value.get("status") or ""),
        "toolCallCount": int(value.get("toolCallCount") or 0),
        "toolResults": _safe_dict_list(value.get("toolResults")),
        "blockedRequests": _safe_dict_list(value.get("blockedRequests")),
        "reviewMarkers": _safe_dict_list(value.get("reviewMarkers")),
        "caveats": [str(item) for item in value.get("caveats", []) if str(item)],
        "plannerMetrics": _safe_dict(value.get("plannerMetrics")),
    }


def dependency_evidence_for_generation_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        "toolName": str(value.get("toolName") or "get_dependency_closure"),
        "dbProfileId": str(value.get("dbProfileId") or ""),
        "snapshotId": value.get("snapshotId"),
        "collectedAt": str(value.get("collectedAt") or ""),
        "rootObject": _safe_dict(value.get("rootObject")),
        "summary": _safe_dict(value.get("summary")),
        "nodes": _safe_dict_list(value.get("nodes")),
        "edges": _safe_dict_list(value.get("edges")),
        "unresolved": _safe_dict_list(value.get("unresolved")),
        "evidenceRefs": _safe_dict_list(value.get("evidenceRefs")),
        "caveats": [str(item) for item in value.get("caveats", []) if str(item)],
        "reviewRequired": bool(value.get("reviewRequired")),
    }


def _safe_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def generation_assumptions(
    agent_run: AgentRunRecord | None,
    *,
    operation_model: Mapping[str, Any] | None = None,
) -> list[str]:
    assumptions = [WORKFLOW_METADATA_NOTE]
    if agent_run:
        assumptions.append(
            "근거 보강 필요: LLM semantic analysis is inferred; treat it as an evidence caveat."
        )
        assumptions.extend(str(item) for item in agent_run.structured_output.get("assumptions", []))
    if operation_model:
        assumptions.append(
            "REVIEW_REQUIRED: SpOperationModel.v0.1 is an internal draft planning contract."
        )
        assumptions.extend(str(item) for item in operation_model.get("assumptions", []))
        assumptions.extend(
            f"REVIEW_REQUIRED: {marker}"
            for marker in operation_model.get("reviewMarkers", [])
            if str(marker)
        )
    return list(dedupe_strings(assumptions))


def llm_trace_summary(agent_run: AgentRunRecord | None) -> dict[str, object] | None:
    if agent_run is None:
        return None
    invocation = agent_run.model_invocation
    return {
        "agentRunId": agent_run.agent_run_id,
        "agentType": agent_run.agent_type,
        "status": agent_run.status,
        "summary": agent_run.summary,
        "provider": invocation.get("provider"),
        "model": invocation.get("model"),
        "modelProfileId": invocation.get("modelProfileId"),
        "modelRegistryRef": invocation.get("modelRegistryRef"),
        "reasoningEffort": invocation.get("reasoningEffort"),
        "promptVersion": invocation.get("promptVersion"),
        "outputSchemaVersion": invocation.get("outputSchemaVersion"),
        "inputHash": invocation.get("inputHash"),
        "promptHash": invocation.get("promptHash"),
        "outputHash": invocation.get("outputHash"),
        "tokenUsage": invocation.get("tokenUsage", {}),
        "latencyMs": invocation.get("latencyMs"),
    }


def _append_ai_tool_components(
    run_payload: AgentRunPayload,
    *,
    ai_tool_component_invocations: tuple[dict[str, object], ...],
    metadata: MetadataCollectionResult,
) -> AgentRunPayload:
    existing_components = tuple(run_payload.model_invocation.component_invocations)
    invocation = dataclass_replace(
        run_payload.model_invocation,
        component_invocations=(
            *ai_tool_component_invocations,
            *existing_components,
        ),
    )
    output = _append_ai_tool_review_markers(
        run_payload.structured_output,
        metadata=metadata,
    )
    invocation = dataclass_replace(
        invocation,
        structured_output=output,
        output_hash=_stable_output_hash(output),
    )
    return dataclass_replace(
        run_payload,
        structured_output=output,
        model_invocation=invocation,
        summary=_summary_with_ai_tool_markers(run_payload.summary, metadata),
    )


def _append_ai_tool_review_markers(
    structured_output: dict[str, object],
    *,
    metadata: MetadataCollectionResult,
) -> dict[str, object]:
    output = {
        key: list(value) if isinstance(value, list) else value
        for key, value in structured_output.items()
    }
    markers = output.setdefault("reviewMarkers", [])
    if not isinstance(markers, list):
        return output
    for evidence in _tool_evidence_blocks(metadata):
        for marker in evidence.get("reviewMarkers", []):
            if not isinstance(marker, dict):
                continue
            marker_code = str(marker.get("code") or "")
            if not marker_code:
                continue
            if any(
                isinstance(existing, dict) and existing.get("code") == marker_code
                for existing in markers
            ):
                continue
            markers.append(
                {
                    "code": marker_code,
                    "message": str(marker.get("message") or ""),
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": [
                        str(ref) for ref in marker.get("evidenceRefs", []) if str(ref)
                    ],
                }
            )
    return output


def _stable_output_hash(output: dict[str, object]) -> str:
    from ai_agent_runtime.models import stable_json_hash

    return stable_json_hash(output)


def _summary_with_ai_tool_markers(
    summary: str,
    metadata: MetadataCollectionResult,
) -> str:
    marker_count = sum(
        len(evidence.get("reviewMarkers", []))
        for evidence in _tool_evidence_blocks(metadata)
    )
    if not marker_count:
        return summary
    return f"{summary}, tool orchestration 근거 caveat {marker_count}개"


def _tool_evidence_blocks(metadata: MetadataCollectionResult) -> list[dict[str, object]]:
    blocks = []
    if isinstance(metadata.ai_tool_evidence, dict):
        blocks.append(metadata.ai_tool_evidence)
    if isinstance(metadata.platform_tool_evidence, dict):
        blocks.append(metadata.platform_tool_evidence)
    return blocks


def procedure_definition_text(metadata: MetadataCollectionResult) -> str | None:
    definition_payload = metadata.procedure_definition or {}
    value = definition_payload.get("definition")
    if not value:
        return None
    return str(value)


def static_analysis_payload(
    definition_text: str | None,
    *,
    source_name: str,
    snapshot_id: str | None,
) -> dict[str, object] | None:
    if not definition_text:
        return None
    source_map = build_procedure_source_map(definition_text, source_name=source_name)
    result = analyze_stored_procedure(
        definition_text,
        source_name=source_name,
        snapshot_id=snapshot_id,
        registry_version_refs=[
            {"registry_type": "PROMPT", "version": "prompt:sp_analysis@0.1.0"},
            {"registry_type": "PROMPT", "version": PROMPT_VERSION},
            {"registry_type": "MODEL", "version": "model:openai_sp_semantic_analysis@0.1.0"},
        ],
    )
    payload = result.model_dump(mode="json")
    payload.pop("source_name", None)
    payload["sourceMap"] = source_map.to_storage_dict()
    payload["analysisCoverage"] = source_map.analysis_coverage
    payload["migrationGuideStaticMetrics"] = migration_guide_static_metrics(
        definition_text,
        source_name=source_name,
    )
    return payload


def source_context_mode_for_options(options: dict[str, object]) -> str:
    if not bool(options.get("allowSpDefinitionToModel", False)):
        return "NONE"
    mode = str(options.get("sourceContextMode") or "RETRIEVED_SPANS").strip().upper()
    return "RETRIEVED_SPANS" if mode == "RETRIEVED_SPANS" else "NONE"


def source_dependency_mode_for_options(options: dict[str, object]) -> str:
    if source_context_mode_for_options(options) != "RETRIEVED_SPANS":
        return "NONE"
    mode = str(
        options.get("sourceDependencyMode") or SOURCE_DEPENDENCY_MODE_CONFIRMED
    ).strip().upper()
    if mode == SOURCE_DEPENDENCY_MODE_CONFIRMED:
        return SOURCE_DEPENDENCY_MODE_CONFIRMED
    return "NONE"


def source_context_packs_for_request(
    definition_text: str | None,
    *,
    request_record: WorkRequestRecord,
    source_name: str,
) -> dict[str, dict[str, object]] | None:
    return source_context_packs_for_options(
        definition_text,
        options=request_record.options,
        source_name=source_name,
    )


def source_context_packs_for_options(
    definition_text: str | None,
    *,
    options: dict[str, object],
    source_name: str,
) -> dict[str, dict[str, object]] | None:
    if not definition_text:
        return None
    mode = source_context_mode_for_options(options)
    if mode != "RETRIEVED_SPANS":
        return None
    source_map = build_procedure_source_map(definition_text, source_name=source_name)
    packs = build_context_packs(
        sql_text=definition_text,
        source_map=source_map,
        target_ref=source_name,
        mode=mode,
    )
    return {stage: pack.to_prompt_dict() for stage, pack in packs.items()}


def dependency_depth_from_env() -> int:
    return min(max(_env_int("LLM_SP_DEPENDENCY_DEPTH", 2), 0), 3)


def dependency_task_limit_from_env() -> int:
    return max(0, _env_int("LLM_SP_MAX_DEPENDENCY_TASKS", 8))


def dependency_procedure_candidates(
    dependency_evidence: Mapping[str, Any],
    *,
    max_depth: int,
    max_tasks: int,
) -> tuple[list[DependencyProcedureCandidate], list[dict[str, Any]]]:
    root = _mapping(dependency_evidence.get("rootObject"))
    nodes = {
        str(node.get("id") or ""): dict(node)
        for node in _mapping_items(dependency_evidence.get("nodes"))
        if node.get("id")
    }
    edges = [dict(edge) for edge in _mapping_items(dependency_evidence.get("edges"))]
    root_id = _dependency_root_id(root, nodes, edges)
    depths = _dependency_node_depths(root_id, edges)
    candidates: list[DependencyProcedureCandidate] = []
    skipped: list[dict[str, Any]] = []

    for unresolved in _mapping_items(dependency_evidence.get("unresolved")):
        skipped.append(
            {
                "targetRef": _dependency_object_ref(unresolved, root_database=root.get("database")),
                "reason": _unresolved_dependency_reason(unresolved),
                "depth": None,
                "database": _dependency_target_database(unresolved, root),
                "sourceScope": _dependency_source_scope(unresolved, {}),
                "evidenceRefs": _dependency_ref_ids(unresolved.get("evidenceRefs")),
            }
        )

    for edge in sorted(edges, key=lambda item: (str(item.get("to")), str(item.get("from")))):
        target_id = str(edge.get("to") or "")
        if target_id == root_id:
            continue
        node = nodes.get(target_id)
        if not node or str(node.get("objectType") or "").upper() != "PROCEDURE":
            continue
        depth = depths.get(target_id, max_depth + 1)
        target_ref = _dependency_object_ref(node, root_database=root.get("database"))
        target_database = _dependency_target_database(node, root)
        source_scope = _dependency_source_scope(node, edge)
        evidence_refs = tuple(
            _dedupe_string_list(
                [
                    *_dependency_ref_ids(edge.get("evidenceRefs")),
                    *_dependency_ref_ids(node.get("evidenceRefs")),
                ]
            )
        )
        reason = _confirmed_procedure_skip_reason(
            edge=edge,
            node=node,
            root=root,
            depth=depth,
            max_depth=max_depth,
        )
        if reason:
            skipped.append(
                {
                    "targetRef": target_ref,
                    "reason": reason,
                    "depth": depth,
                    "database": target_database,
                    "sourceScope": source_scope,
                    "evidenceRefs": list(evidence_refs),
                }
            )
            continue
        candidates.append(
            DependencyProcedureCandidate(
                target_ref=target_ref,
                schema=str(node.get("schema") or ""),
                name=str(node.get("name") or ""),
                depth=depth,
                database=target_database,
                source_scope=source_scope,
                node=dict(node),
                edge=dict(edge),
                evidence_refs=evidence_refs,
            )
        )

    if max_tasks < len(candidates):
        overflow = candidates[max_tasks:]
        candidates = candidates[:max_tasks]
        for candidate in overflow:
            skipped.append(
                {
                    "targetRef": candidate.target_ref,
                    "reason": "DEPENDENCY_TASK_LIMIT_EXCEEDED",
                    "depth": candidate.depth,
                    "database": candidate.database,
                    "sourceScope": candidate.source_scope,
                    "evidenceRefs": list(candidate.evidence_refs),
                }
            )
    return candidates, skipped


def dependency_child_metadata(
    *,
    request_record: WorkRequestRecord,
    metadata: MetadataCollectionResult,
    candidate: DependencyProcedureCandidate,
    definition_payload: Mapping[str, Any],
    tool_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    sanitized_definition = dict(definition_payload)
    sanitized_definition.pop("definition", None)
    evidence_refs = _safe_evidence_refs(
        [
            *candidate.node.get("evidenceRefs", []),
            *candidate.edge.get("evidenceRefs", []),
            *((tool_payload or {}).get("evidenceRefs") or []),
        ]
    )
    return {
        "dbProfileId": request_record.db_profile_id,
        "objectRef": candidate.target_ref,
        "database": candidate.database,
        "sourceScope": candidate.source_scope,
        "snapshotId": metadata.snapshot_id,
        "collectedAt": metadata.collected_at,
        "procedureDefinition": sanitized_definition,
        "dependencyEvidence": {
            "toolName": "get_dependency_closure",
            "rootObject": metadata.dependency_evidence.get("rootObject")
            if metadata.dependency_evidence
            else {},
            "nodes": [candidate.node],
            "edges": [candidate.edge],
            "unresolved": [],
            "summary": {
                "maxDepth": candidate.depth,
                "nodeCount": 1,
                "edgeCount": 1,
                "reviewRequiredCount": 0,
            },
            "evidenceRefs": evidence_refs,
            "reviewRequired": False,
        },
        "evidenceRefs": evidence_refs,
        "notes": [
            "Dependency procedure metadata is collected through the internal read-only "
            "MCP registry.",
            "Raw dependency procedure definition is transient model input only.",
        ],
    }


def dependency_review_markers(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    markers = []
    for item in items:
        reason = str(item.get("reason") or "DEPENDENCY_SEMANTIC_ANALYSIS_INCOMPLETE")
        target_ref = str(item.get("targetRef") or "REVIEW_REQUIRED")
        code = (
            "DEPENDENCY_SEMANTIC_ANALYSIS_INCOMPLETE"
            if reason in {"DEFINITION_UNAVAILABLE", "SEMANTIC_ANALYSIS_FAILED"}
            else "DEPENDENCY_MANUAL_REVIEW_REQUIRED"
        )
        markers.append(
            {
                "code": code,
                "message": f"{target_ref} dependency analysis skipped: {reason}.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": list(item.get("evidenceRefs") or []),
            }
        )
    return _dedupe_markers(markers)


def _append_dependency_semantic_analysis(
    run_payload: AgentRunPayload,
    *,
    dependency_analysis: Mapping[str, Any],
) -> AgentRunPayload:
    output = {
        key: list(value) if isinstance(value, list) else value
        for key, value in run_payload.structured_output.items()
    }
    analyzed_targets = [
        dict(item)
        for item in dependency_analysis.get("analyzedTargets", [])
        if isinstance(item, Mapping)
    ]
    markers = [
        dict(item)
        for item in dependency_analysis.get("reviewMarkers", [])
        if isinstance(item, Mapping)
    ]
    for item in analyzed_targets:
        target_ref = str(item.get("targetRef") or "REVIEW_REQUIRED")
        refs = _safe_claim_refs(item.get("evidenceRefs"))
        child_output = _mapping(item.get("structuredOutput"))
        child_marker_count = len(_mapping_items(child_output.get("reviewMarkers")))
        output.setdefault("conversionGuidance", []).append(
            {
                "code": f"CALLED_PROCEDURE_STRATEGY_{_code_suffix(target_ref)}",
                "summary": (
                    f"{target_ref} 의존 프로시저는 child semantic run으로 별도 분석되었습니다. "
                    "Java/MyBatis 전환 시 wrapper 호출 유지, 서비스 분리, 또는 수동 재설계 여부를 "
                    "검토해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": refs,
            }
        )
        output.setdefault("migrationGuideInsights", []).append(
            {
                "section": f"dependency_child_analysis_{_code_suffix(target_ref).lower()}",
                "summary": (
                    f"{target_ref} child 분석 결과를 migration guide의 called procedure strategy에 "
                    "반영해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": refs,
                "guideElement": "called_procedure_strategy",
                "targetRef": target_ref,
                "riskArea": "dependency_call_flow",
                "whatToExtractNext": (
                    "transaction boundary, input/output DTO, nested DML/result shape를 "
                    "child AgentRun evidence와 대조할 수 있게 보강합니다."
                ),
            }
        )
        if child_marker_count:
            markers.append(
                {
                    "code": "DEPENDENCY_CHILD_REVIEW_MARKERS_PRESENT",
                    "message": f"{target_ref} child semantic run has evidence caveat markers.",
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": refs,
                }
            )
    output.setdefault("reviewMarkers", []).extend(markers)
    output["reviewMarkers"] = _dedupe_markers(output.get("reviewMarkers", []))
    output.setdefault("assumptions", []).append(
        "confirmed dependency procedure semantic outputs are draft-only evidence aids.",
    )
    output["assumptions"] = list(dedupe_strings(str(item) for item in output["assumptions"]))

    component = {
        "stage": "dependency_semantic_reduce",
        "status": "SUCCEEDED",
        "sourceContextSummary": {
            "mode": "RETRIEVED_SPANS" if dependency_analysis.get("enabled") else "NONE",
            "budgetStatus": "WITHIN_BUDGET",
            "selectedSpanCount": 0,
            "skippedSpanCount": int(dependency_analysis.get("skippedCount") or 0),
            "dependencyAnalysis": dependency_analysis_summary(dependency_analysis),
            "reviewMarkers": markers,
        },
    }
    invocation = dataclass_replace(
        run_payload.model_invocation,
        structured_output=output,
        output_hash=stable_json_hash(output),
        component_invocations=(
            *run_payload.model_invocation.component_invocations,
            component,
        ),
    )
    return dataclass_replace(
        run_payload,
        structured_output=output,
        model_invocation=invocation,
        summary=(
            f"{run_payload.summary} Dependency child analysis "
            f"{dependency_analysis.get('analyzedCount', 0)}건을 반영했습니다."
        ),
    )


def dependency_analysis_summary(dependency_analysis: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": str(dependency_analysis.get("mode") or "NONE"),
        "requestedDepth": int(dependency_analysis.get("requestedDepth") or 0),
        "maxTasks": int(dependency_analysis.get("maxTasks") or 0),
        "selectedCount": int(dependency_analysis.get("selectedCount") or 0),
        "analyzedCount": int(dependency_analysis.get("analyzedCount") or 0),
        "skippedCount": int(dependency_analysis.get("skippedCount") or 0),
        "childRunCount": int(dependency_analysis.get("childRunCount") or 0),
        "reusedChildRunCount": int(dependency_analysis.get("reusedChildRunCount") or 0),
        "analyzedTargets": [
            {
                "targetRef": str(item.get("targetRef") or ""),
                "targetKey": item.get("targetKey"),
                "agentRunId": str(item.get("agentRunId") or ""),
                "depth": item.get("depth"),
                "database": item.get("database"),
                "sourceScope": item.get("sourceScope"),
                "evidenceRefs": list(item.get("evidenceRefs") or []),
                "sourceContextSummary": dict(item.get("sourceContextSummary") or {}),
                "reused": bool(item.get("reused")),
            }
            for item in dependency_analysis.get("analyzedTargets", [])
            if isinstance(item, Mapping)
        ],
        "skippedTargets": [
            {
                "targetRef": str(item.get("targetRef") or ""),
                "reason": str(item.get("reason") or ""),
                "depth": item.get("depth"),
                "database": item.get("database"),
                "sourceScope": item.get("sourceScope"),
                "evidenceRefs": list(item.get("evidenceRefs") or []),
            }
            for item in dependency_analysis.get("skippedTargets", [])
            if isinstance(item, Mapping)
        ],
    }


def _dependency_root_id(
    root: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> str:
    for node_id, node in nodes.items():
        if (
            _same_text(node.get("schema"), root.get("schema"))
            and _same_text(node.get("name"), root.get("name"))
            and _same_text(node.get("objectType"), root.get("objectType"))
        ):
            return node_id
    if edges:
        return str(edges[0].get("from") or "")
    return ""


def _dependency_node_depths(
    root_id: str,
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    if not root_id:
        return {}
    depths = {root_id: 0}
    queue = [root_id]
    while queue:
        source = queue.pop(0)
        next_depth = depths[source] + 1
        for edge in edges:
            if str(edge.get("from") or "") != source:
                continue
            if str(edge.get("resolutionStatus") or "").upper() != "CONFIRMED":
                continue
            target = str(edge.get("to") or "")
            if not target:
                continue
            if target not in depths or next_depth < depths[target]:
                depths[target] = next_depth
                queue.append(target)
    return depths


def _confirmed_procedure_skip_reason(
    *,
    edge: Mapping[str, Any],
    node: Mapping[str, Any],
    root: Mapping[str, Any],
    depth: int,
    max_depth: int,
) -> str | None:
    if depth > max_depth:
        return "DEPENDENCY_DEPTH_EXCEEDED"
    if str(edge.get("resolutionStatus") or "").upper() != "CONFIRMED":
        return "UNCONFIRMED_DEPENDENCY"
    if str(node.get("reviewStatus") or "").upper() not in {"", "CONFIRMED"}:
        return "REVIEW_REQUIRED_DEPENDENCY"
    strategy = str(edge.get("resolutionStrategy") or "").upper()
    if "CALLER" in strategy:
        return "CALLER_DEPENDENT_REFERENCE"
    if node.get("server") or node.get("referencedServer"):
        return "CROSS_SERVER_REFERENCE"
    root_database = root.get("database")
    node_database = node.get("database") or node.get("referencedDatabase")
    if root_database and node_database and not _same_text(root_database, node_database):
        if not _is_safe_cross_database_procedure(edge=edge, node=node):
            return "CROSS_DATABASE_DEFINITION_UNSUPPORTED"
    if not node.get("schema") or not node.get("name"):
        return "UNRESOLVED_REFERENCE"
    return None


def _is_safe_cross_database_procedure(
    *,
    edge: Mapping[str, Any],
    node: Mapping[str, Any],
) -> bool:
    source_scope = (_dependency_source_scope(node, edge) or "").upper()
    strategy = str(edge.get("resolutionStrategy") or node.get("resolutionStrategy") or "").upper()
    confidence = str(edge.get("resolutionConfidence") or node.get("resolutionConfidence") or "")
    return (
        source_scope == "SAME_SERVER_CROSS_DATABASE"
        and strategy == "SAME_SERVER_CROSS_DATABASE_CATALOG"
        and confidence.upper() in {"", "HIGH"}
    )


def _unresolved_dependency_reason(item: Mapping[str, Any]) -> str:
    dependency_type = str(item.get("dependencyType") or "").upper()
    strategy = str(item.get("resolutionStrategy") or "").upper()
    if "DYNAMIC" in dependency_type or "DYNAMIC" in strategy:
        return "DYNAMIC_SQL_REVIEW_REQUIRED"
    if bool(item.get("isAmbiguous")) or "AMBIGUOUS" in strategy:
        return "AMBIGUOUS_REFERENCE"
    if "CALLER" in strategy:
        return "CALLER_DEPENDENT_REFERENCE"
    if item.get("server") or item.get("referencedServer"):
        return "CROSS_SERVER_REFERENCE"
    if item.get("database") or item.get("referencedDatabase"):
        return "CROSS_DATABASE_DEFINITION_UNSUPPORTED"
    return "UNRESOLVED_REFERENCE"


def _dependency_object_ref(
    item: Mapping[str, Any],
    *,
    root_database: Any | None = None,
) -> str:
    schema = str(item.get("schema") or "").strip()
    name = str(item.get("name") or "").strip()
    if schema and name:
        database = str(item.get("database") or item.get("referencedDatabase") or "").strip()
        if database and (
            root_database is None
            or not _same_text(database, root_database)
            or str(item.get("sourceScope") or "").upper() == "SAME_SERVER_CROSS_DATABASE"
        ):
            return f"{database}.{schema}.{name}"
        return f"{schema}.{name}"
    if name:
        return name
    return "REVIEW_REQUIRED"


def _dependency_target_database(
    item: Mapping[str, Any],
    root: Mapping[str, Any],
) -> str | None:
    database = str(item.get("database") or item.get("referencedDatabase") or "").strip()
    if not database:
        return None
    root_database = root.get("database")
    source_scope = str(item.get("sourceScope") or "").upper()
    if source_scope == "SAME_SERVER_CROSS_DATABASE":
        return database
    if root_database and not _same_text(database, root_database):
        return database
    return None


def _dependency_source_scope(
    node: Mapping[str, Any],
    edge: Mapping[str, Any],
) -> str | None:
    source_scope = str(node.get("sourceScope") or edge.get("sourceScope") or "").strip()
    return source_scope or None


def _dependency_ref_ids(value: Any) -> list[str]:
    refs = []
    for item in _mapping_items(value):
        object_ref = str(
            item.get("objectRef")
            or item.get("object_ref")
            or item.get("objectName")
            or item.get("id")
            or ""
        ).strip()
        locator = str(item.get("locator") or item.get("path") or "").strip()
        if object_ref or locator:
            refs.append(f"metadata:{object_ref}:{locator}")
    return _dedupe_string_list(refs)


def _safe_evidence_refs(values: Sequence[Any]) -> list[dict[str, Any]]:
    refs = []
    seen: set[tuple[str, str, str | None]] = set()
    for value in values:
        if not isinstance(value, Mapping):
            continue
        object_ref = str(
            value.get("objectRef")
            or value.get("object_ref")
            or value.get("objectName")
            or value.get("id")
            or "metadata"
        )
        locator = str(value.get("locator") or value.get("path") or "mssql-mcp")
        snapshot_id = value.get("snapshotId")
        key = (object_ref, locator, str(snapshot_id) if snapshot_id else None)
        if key in seen:
            continue
        item = {
            "type": str(value.get("type") or "MSSQL_METADATA"),
            "objectRef": object_ref,
            "locator": locator,
        }
        if snapshot_id:
            item["snapshotId"] = str(snapshot_id)
        refs.append(item)
        seen.add(key)
    return refs


def _safe_claim_refs(value: Any) -> list[str]:
    forbidden_prefixes = ("prompt.", "modelInvocation.")
    forbidden_values = {"metadata.snapshot", "static.analysis"}
    refs = [str(item) for item in (value or []) if str(item).strip()]
    return [
        ref
        for ref in _dedupe_string_list(refs)
        if not ref.startswith(forbidden_prefixes) and ref not in forbidden_values
    ]


def _dedupe_markers(items: Sequence[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        marker = dict(item)
        key = (str(marker.get("code") or ""), str(marker.get("message") or ""))
        if key in seen:
            continue
        marker["evidenceRefs"] = _safe_claim_refs(marker.get("evidenceRefs"))
        deduped.append(marker)
        seen.add(key)
    return deduped


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _dedupe_string_list(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            deduped.append(text)
            seen.add(text)
    return deduped


def _same_text(left: Any, right: Any) -> bool:
    return str(left or "").casefold() == str(right or "").casefold()


def _code_suffix(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").upper()
    return cleaned or "REVIEW_REQUIRED"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def system_code(db_profile_id: str) -> str:
    cleaned = "".join(char for char in db_profile_id.upper() if char.isalnum())
    return cleaned or "PLF"


def pascal_case(value: str) -> str:
    tokens = [token for token in re.split(r"[^0-9A-Za-z]+|_", value) if token]
    if not tokens:
        return "ReviewRequiredEntity"
    stripped = [token for token in tokens if token.lower() not in {"usp", "sp"}]
    source = stripped or tokens
    return "".join(token[:1].upper() + token[1:] for token in source)


def kebab_case(value: str) -> str:
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", value)
    return "-".join(word.lower() for word in words) or "review-required"
