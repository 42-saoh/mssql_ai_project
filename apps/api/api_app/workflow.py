from __future__ import annotations

import re

from ai_agent_domain import ArtifactType, JobStatus, RequestedOutputType, WorkflowStepType
from ai_agent_generation import (
    GenerationContext,
    RenderedArtifact,
    RenderedBundle,
    render_artifact,
    render_java_mybatis_sp_wrapper,
)
from ai_agent_generation.models import GENERATOR_VERSION
from ai_agent_validation import validate_artifact, validate_publish_gate

from api_app.metadata_gateway import McpMetadataGateway, MetadataCollectionResult, MetadataGateway
from api_app.repositories import (
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


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository,
        metadata_gateway: MetadataGateway | None = None,
    ) -> None:
        self.repository = repository
        self.metadata_gateway = metadata_gateway or McpMetadataGateway()

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
            options=dict(request.options),
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
                code=exc.__class__.__name__,
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
        self.repository.transition_job(
            job_id,
            status=JobStatus.GENERATING,
            current_step=WorkflowStepType.GENERATE,
        )
        artifacts = self._generate_artifacts(job_id, request, metadata)

        self.repository.transition_job(
            job_id,
            status=JobStatus.VALIDATING,
            current_step=WorkflowStepType.VALIDATE,
        )
        reports = [self.validate_artifact(artifact.artifact_id) for artifact in artifacts]
        next_status = (
            JobStatus.FAILED
            if any(report.status == "FAILED" for report in reports)
            else JobStatus.REVIEW_PENDING
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
        if (
            validation_report_id is not None
            and (
                latest_validation is None
                or validation_report_id != latest_validation.validation_report_id
            )
        ):
            raise ValueError("validationReportId must match the latest artifact validation.")
        if decision == "APPROVE":
            if latest_validation is None:
                raise ValueError("APPROVE requires a PASSED validation report.")
            if latest_validation.status != "PASSED":
                raise ValueError("APPROVE requires latest validation status PASSED.")
        return self.repository.add_approval(
            artifact_id=artifact_id,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
            validation_report_id=validation_report_id,
            correlation_id=correlation_id,
        )

    def evaluate_publish_gate(self, artifact_id: str) -> ValidationReportRecord:
        self._require_artifact(artifact_id)
        validation = self.repository.latest_validation_for(artifact_id)
        approval = self.repository.latest_approval_for(artifact_id)
        gate_report = validate_publish_gate(
            artifact_id=artifact_id,
            validation_status=validation.status if validation else None,
            approval_decision=approval.decision if approval else None,
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
            payload={"status": record.status, "storageResult": record.storage_result},
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
        self.repository.save_metadata_collection(
            job_id=job_id,
            status=metadata.status,
            payload=metadata.as_dict(),
        )
        return metadata

    def _generate_artifacts(
        self,
        job_id: str,
        request: WorkRequestRecord,
        metadata: MetadataCollectionResult,
    ) -> list[ArtifactRecord]:
        context = generation_context_from_request(request, metadata)
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
                    )
                    for artifact_type in artifact_types_for_requested_output(output)
                )
        return artifacts

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
            assumptions=tuple(rendered.assumptions) + (WORKFLOW_METADATA_NOTE,),
            review_required=rendered.review_required,
            extra=dict(rendered.extra),
        )

    def _store_java_mybatis_bundle(
        self,
        job_id: str,
        bundle: RenderedBundle,
    ) -> list[ArtifactRecord]:
        assumptions = (
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
            extra={"source": "api_contract_placeholder", "metadata": metadata.as_dict()},
        )

    def _require_artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self.repository.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        return artifact


def generation_context_from_request(
    request: WorkRequestRecord,
    metadata: MetadataCollectionResult | None = None,
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
            },
            "evidence": {
                "sources": generation_evidence_sources(metadata, sp_name),
                "assumptions": [WORKFLOW_METADATA_NOTE],
            },
        }
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
) -> list[dict[str, str]]:
    if not metadata:
        return [
            {
                "type": "storedProcedure",
                "name": sp_name,
                "reason": "request target only; metadata collection unavailable",
            }
        ]
    sources = [
        {
            "type": "storedProcedure",
            "name": sp_name,
            "reason": metadata.status,
        }
    ]
    sources.extend(
        {
            "type": "table",
            "name": f"{table['schema']}.{table['tableName']}",
            "reason": "MSSQL MCP table schema metadata",
        }
        for table in metadata.table_schemas
        if table.get("schema") and table.get("tableName")
    )
    return sources


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
