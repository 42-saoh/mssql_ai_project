from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import replace as dataclass_replace

from ai_agent_analysis import analyze_stored_procedure
from ai_agent_domain import ArtifactType, JobStatus, RequestedOutputType, WorkflowStepType
from ai_agent_generation import (
    GenerationContext,
    RenderedArtifact,
    RenderedBundle,
    render_artifact,
    render_java_mybatis_sp_wrapper,
)
from ai_agent_generation.models import GENERATOR_VERSION
from ai_agent_runtime import (
    AgentRunPayload,
    ModelGateway,
    ModelGatewayError,
    attach_planner_metrics_to_ai_tool_evidence,
    build_model_gateway_from_env,
    build_semantic_analysis_run,
)
from ai_agent_validation import (
    ValidationCheck,
    ValidationCheckResult,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
    build_reviewer_checklist,
    summarize_validation_report,
    validate_artifact,
    validate_publish_gate,
)

from api_app.ai_tool_orchestrator import AiToolOrchestrator
from api_app.metadata_gateway import McpMetadataGateway, MetadataCollectionResult, MetadataGateway
from api_app.repositories import (
    AgentRunRecord,
    ApprovalRecordData,
    ArtifactRecord,
    JobRecord,
    ValidationReportRecord,
    WorkflowRepository,
    WorkRequestRecord,
)
from api_app.schemas import SPAnalysisRequest
from api_app.tracking import (
    IdempotencyConflictError,
    RequestTrackingContext,
    request_payload_hash,
)

WORKFLOW_METADATA_NOTE = (
    "REVIEW_REQUIRED: metadata is collected through the MSSQL MCP registry boundary "
    "and persisted through the platform DB workflow repository for this integration slice."
)


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
    ) -> None:
        self.repository = repository
        self.metadata_gateway = metadata_gateway or McpMetadataGateway()
        self.model_gateway = model_gateway or build_model_gateway_from_env()
        self.ai_tool_orchestrator = AiToolOrchestrator(model_gateway=self.model_gateway)

    def submit_sp_analysis(
        self,
        request: SPAnalysisRequest,
        tracking: RequestTrackingContext | None = None,
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
        request_record = self.repository.create_request(
            db_profile_id=request.db_profile_id,
            target=request.target.to_response(),
            outputs=tuple(output.value for output in request.outputs),
            options=request.options.to_response(),
            request_hash=request_hash,
            correlation_id=tracking.correlation_id,
            idempotency_key=tracking.idempotency_key,
        )
        job = self.repository.create_job(
            request_record.request_id,
            correlation_id=tracking.correlation_id,
        )

        try:
            job = self.run_initial_workflow(job.job_id, request_record)
        except Exception as exc:  # pragma: no cover - defensive failure state
            job = self.repository.fail_job(
                job.job_id,
                code=str(getattr(exc, "code", exc.__class__.__name__)),
                message=str(exc),
            )
        request_record.status = job.status
        return request_record, job

    def run_initial_workflow(
        self,
        job_id: str,
        request: WorkRequestRecord,
    ) -> JobRecord:
        self.repository.transition_job(
            job_id,
            status=JobStatus.COLLECTING_METADATA,
            current_step=WorkflowStepType.COLLECT_METADATA,
        )
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
        orchestration = self.ai_tool_orchestrator.run(
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
        )
        metadata = orchestration.metadata
        agent_run = self._run_llm_semantic_analysis(
            job_id,
            request_record=request,
            metadata=metadata,
            static_analysis=static_analysis,
            ai_tool_component_invocations=orchestration.component_invocations,
        )
        metadata = metadata_with_planner_metrics(
            metadata,
            agent_run=agent_run,
            component_invocations=orchestration.component_invocations,
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
        artifacts = self._generate_artifacts(job_id, request, metadata, agent_run)

        self.repository.transition_job(
            job_id,
            status=JobStatus.VALIDATING,
            current_step=WorkflowStepType.VALIDATE,
        )
        reports = [self.validate_artifact(artifact.artifact_id) for artifact in artifacts]
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

    def record_approval_decision(
        self,
        *,
        artifact_id: str,
        decision: str,
        reviewer: str,
        comment: str,
        validation_report_id: str | None,
        correlation_id: str | None = None,
    ) -> ApprovalRecordData:
        self._require_artifact(artifact_id)
        latest_validation = self.repository.latest_validation_for(artifact_id)
        if latest_validation is None:
            raise ValueError("Approval decision requires the latest artifact validation.")
        if validation_report_id is not None and (
            validation_report_id != latest_validation.validation_report_id
        ):
            raise ValueError("validationReportId must match the latest artifact validation.")
        if decision == "APPROVE":
            if latest_validation.status != "PASSED":
                raise ValueError("APPROVE requires latest validation status PASSED.")
        validation_report = validation_record_to_report(latest_validation)
        reviewer_checklist = [
            item.as_dict()
            for item in build_reviewer_checklist(
                validation_report,
                decision=decision,
                reviewer=reviewer,
                comment=comment,
            )
        ]
        return self.repository.add_approval(
            artifact_id=artifact_id,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
            validation_report_id=latest_validation.validation_report_id,
            reviewer_checklist=reviewer_checklist,
            validation_summary=summarize_validation_report(validation_report),
            correlation_id=correlation_id,
        )

    def evaluate_publish_gate(
        self,
        artifact_id: str,
        *,
        operation: str = "publish",
    ) -> ValidationReportRecord:
        artifact = self._require_artifact(artifact_id)
        validation = self.repository.latest_validation_for(artifact_id)
        approval = self.repository.latest_approval_for(artifact_id)
        gate_report = validate_publish_gate(
            artifact_id=artifact_id,
            validation_status=validation.status if validation else None,
            approval_decision=approval.decision if approval else None,
            operation=operation,
        )
        record = self.repository.save_validation_report(
            artifact_id=artifact_id,
            status=gate_report.status.value,
            checks=[check.as_dict() for check in gate_report.checks],
            missing_evidence=list(gate_report.missing_evidence),
            manual_review_points=list(gate_report.manual_review_points),
        )
        self.repository.record_audit_event(
            action="PUBLISH_GATE_EVALUATED",
            target_type="ARTIFACT",
            target_ref_id=artifact_id,
            payload={
                "status": record.status,
                "storageResult": record.storage_result,
                "operation": operation,
            },
            correlation_id=(
                job.correlation_id
                if (job := self.repository.get_job(artifact.job_id)) is not None
                else None
            ),
        )
        return record

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
    ) -> list[ArtifactRecord]:
        context = generation_context_from_request(request, metadata, agent_run)
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
                artifacts.extend(
                    self._store_java_mybatis_bundle(
                        job_id,
                        render_java_mybatis_sp_wrapper(context),
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

    def _run_llm_semantic_analysis(
        self,
        job_id: str,
        *,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        static_analysis: dict[str, object],
        ai_tool_component_invocations: tuple[dict[str, object], ...] = (),
    ) -> AgentRunRecord | None:
        if not bool(request_record.options.get("useLlmAnalysis", False)):
            return None
        target = request_record.target
        object_ref = f"{target['schema']}.{target['name']}"
        definition_text = procedure_definition_text(metadata)
        definition_for_model = (
            definition_text
            if bool(request_record.options.get("allowSpDefinitionToModel", False))
            else None
        )
        if (
            os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1"
            and bool(request_record.options.get("allowSpDefinitionToModel", False))
            and os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1"
        ):
            raise ModelGatewayError(
                "LLM_ALLOW_SP_TEXT=1 is required before high-quality live analysis.",
                code="LLM_SP_TEXT_NOT_ALLOWED",
            )
        try:
            run_payload = build_semantic_analysis_run(
                target_ref=object_ref,
                metadata=metadata.as_dict(),
                static_analysis=static_analysis,
                procedure_definition=definition_for_model,
                model_gateway=self.model_gateway,
                profile_id=str(request_record.options.get("llmProfileId") or ""),
            )
        except ModelGatewayError:
            raise
        if ai_tool_component_invocations or (
            metadata.ai_tool_evidence
            and metadata.ai_tool_evidence.get("reviewMarkers")
        ):
            run_payload = _append_ai_tool_components(
                run_payload,
                ai_tool_component_invocations=ai_tool_component_invocations,
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
        )

    def _store_rendered_artifact(
        self,
        job_id: str,
        rendered: RenderedArtifact,
    ) -> ArtifactRecord:
        return self.repository.add_artifact(
            job_id=job_id,
            artifact_type=ArtifactType(rendered.artifact_type_value),
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
            artifacts.append(
                self.repository.add_artifact(
                    job_id=job_id,
                    artifact_type=file.artifact_type,
                    title=file.path,
                    content=file.content,
                    evidence_refs=[],
                    generator_version=bundle.manifest.generator_version,
                    registry_refs=tuple(bundle.manifest.registry_refs),
                    assumptions=assumptions,
                    review_required=True,
                    extra={
                        "requestedOutputType": bundle.requested_output_type,
                        "source": "java_mybatis_sp_wrapper_bundle",
                    },
                )
            )
        return artifacts

    def _store_contract_placeholder_artifact(
        self,
        job_id: str,
        artifact_type: ArtifactType,
        request: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        agent_run: AgentRunRecord | None = None,
    ) -> ArtifactRecord:
        target = request.target
        object_ref = f"{target['schema']}.{target['name']}"
        metadata_lines = metadata_summary_lines(metadata)
        content = "\n".join(
            [
                f"# {artifact_type.value} Draft",
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
                "## assumptions_and_review",
                f"- {WORKFLOW_METADATA_NOTE}",
                (
                    "- REVIEW_REQUIRED: package-backed renderer is not available for this "
                    "artifact type."
                ),
                "",
                "## review_checklist",
                "- [ ] reviewer_confirms_contract_placeholder_boundary",
                "",
            ]
        )
        return self.repository.add_artifact(
            job_id=job_id,
            artifact_type=artifact_type,
            title=f"{artifact_type.value} Draft",
            content=content,
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
    return GenerationContext.from_mapping(
        {
            "sampleId": request.request_id,
            "request": {
                "systemCode": system_code(request.db_profile_id),
                "businessCodeLv1": "workflow",
                "businessCodeLv2": "draft",
                "entityName": entity_name,
                "resourceName": kebab_case(entity_name),
                "description": f"{sp_name} draft workflow output",
                "generationMode": "spWrapper",
                "tableName": table_name,
                "spName": sp_name,
                "columns": columns,
                "inputParams": input_params,
                "resultShape": result_shape,
                "pkColumns": [],
                "authorId": "AI",
                "llmAnalysis": agent_run.structured_output if agent_run else None,
                "llmTrace": llm_trace_summary(agent_run),
                "dependencyEvidence": dependency_evidence_for_generation(metadata),
                "aiToolEvidence": ai_tool_evidence_for_generation(metadata),
            },
            "evidence": {
                "sources": generation_evidence_sources(metadata, sp_name, agent_run),
                "assumptions": generation_assumptions(agent_run),
            },
        }
    )


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
    if output == RequestedOutputType.DTO_MODEL_DRAFT.value:
        return (ArtifactType.DTO_DRAFT, ArtifactType.VO_DRAFT, ArtifactType.MODEL_DRAFT)
    if output == RequestedOutputType.DDL_DRAFT.value:
        return (ArtifactType.DDL_DRAFT,)
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
    return sanitized


def metadata_with_planner_metrics(
    metadata: MetadataCollectionResult,
    *,
    agent_run: AgentRunRecord | None,
    component_invocations: tuple[dict[str, object], ...],
) -> MetadataCollectionResult:
    if not isinstance(metadata.ai_tool_evidence, dict):
        return metadata
    evidence = attach_planner_metrics_to_ai_tool_evidence(
        metadata.ai_tool_evidence,
        deterministic_facts=metadata.deterministic_facts,
        component_invocations=component_invocations,
        structured_output=agent_run.structured_output if agent_run else None,
    )
    return dataclass_replace(metadata, ai_tool_evidence=evidence)


def metadata_detail_lines(metadata: MetadataCollectionResult) -> list[str]:
    if not metadata.table_schemas:
        return ["- REVIEW_REQUIRED: table schema metadata was not available."]
    lines: list[str] = []
    for table in metadata.table_schemas:
        table_ref = f"{table.get('schema')}.{table.get('tableName')}"
        lines.append(f"- Table: `{table_ref}`")
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
) -> list[dict[str, str | None]]:
    if not metadata:
        sources: list[dict[str, str | None]] = [
            {
                "type": "storedProcedure",
                "name": sp_name,
                "reason": "request target only; metadata collection unavailable",
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
                "reason": "MSSQL MCP table schema metadata",
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
                "reason": "MSSQL MCP dependency closure evidence",
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


def generation_assumptions(agent_run: AgentRunRecord | None) -> list[str]:
    assumptions = [WORKFLOW_METADATA_NOTE]
    if agent_run:
        assumptions.append(
            "REVIEW_REQUIRED: LLM semantic analysis is inferred and remains a validation caveat."
        )
        assumptions.extend(str(item) for item in agent_run.structured_output.get("assumptions", []))
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
    evidence = metadata.ai_tool_evidence or {}
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
    evidence = metadata.ai_tool_evidence or {}
    marker_count = len(evidence.get("reviewMarkers", []))
    if not marker_count:
        return summary
    return f"{summary}, {marker_count} AI tool orchestration review markers"


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
    result = analyze_stored_procedure(
        definition_text,
        source_name=source_name,
        snapshot_id=snapshot_id,
        registry_version_refs=[
            {"registry_type": "PROMPT", "version": "prompt:sp_analysis@0.1.0"},
            {"registry_type": "PROMPT", "version": "prompt:sp_semantic_analysis@0.3.0"},
            {"registry_type": "MODEL", "version": "model:openai_sp_semantic_analysis@0.1.0"},
        ],
    )
    payload = result.model_dump(mode="json")
    payload.pop("source_name", None)
    return payload


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
