from __future__ import annotations

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from api_app.lifecycle import WorkflowStateError
from api_app.schemas import SPAnalysisRequest
from api_app.tracking import IdempotencyConflictError, RequestTrackingContext
from api_app.workflow import WorkflowService

from tests.unit.api.fake_repository import MemoryWorkflowRepository


def _request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": outputs
            or [
                "SP_ANALYSIS_DOCUMENT",
                "DEPENDENCY_REPORT",
                "JAVA_MYBATIS_DRAFT",
            ],
            "options": {"includeEvidenceRefs": True},
        }
    )


def _fixture_request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": outputs or ["SP_ANALYSIS_DOCUMENT", "TABLE_COLUMN_METADATA"],
            "options": {"includeEvidenceRefs": True},
        }
    )


def test_submit_runs_initial_workflow_and_exposes_persisted_artifact_types() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(_request())

    assert request_record.status == JobStatus.REVIEW_PENDING
    assert job.status == JobStatus.REVIEW_PENDING
    assert [status.value for status, _step in job.transitions] == [
        "COLLECTING_METADATA",
        "ANALYZING",
        "GENERATING",
        "VALIDATING",
        "REVIEW_PENDING",
    ]

    artifact_types = {artifact.type for artifact in repository.artifacts.values()}
    assert ArtifactType.SP_ANALYSIS_DOC in artifact_types
    assert ArtifactType.DEPENDENCY_REPORT in artifact_types
    assert ArtifactType.DTO_DRAFT in artifact_types
    assert ArtifactType.SERVICE_DRAFT in artifact_types
    assert ArtifactType.MAPPER_INTERFACE in artifact_types
    assert ArtifactType.MAPPER_XML in artifact_types
    public_types = {artifact.type.value for artifact in repository.artifacts.values()}
    assert "JAVA_MYBATIS_DRAFT" not in public_types
    assert all(artifact.latest_validation_report_id for artifact in repository.artifacts.values())
    assert repository.audit_events
    assert any(event.action == "METADATA_COLLECTED" for event in repository.audit_events)


def test_submit_replays_same_idempotency_key_for_same_payload() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    first_request, first_job = service.submit_sp_analysis(
        _request(),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit-1",
            idempotency_key="idem-p09-same",
        ),
    )
    replay_request, replay_job = service.submit_sp_analysis(
        _request(),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit-2",
            idempotency_key="idem-p09-same",
        ),
    )

    assert replay_request.request_id == first_request.request_id
    assert replay_job.job_id == first_job.job_id
    assert len(repository.requests) == 1
    assert repository.requests[first_request.request_id].request_hash
    assert repository.requests[first_request.request_id].idempotency_key == "idem-p09-same"
    replay_audit = repository.audit_events[-1]
    assert replay_audit.action == "IDEMPOTENT_REQUEST_REPLAYED"
    assert replay_audit.correlation_id == "corr-submit-2"


def test_submit_rejects_idempotency_key_reused_for_different_payload() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(
        _request(["SP_ANALYSIS_DOCUMENT"]),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit",
            idempotency_key="idem-p09-conflict",
        ),
    )

    with pytest.raises(IdempotencyConflictError, match="different request payload"):
        service.submit_sp_analysis(
            _request(["DEPENDENCY_REPORT"]),
            tracking=RequestTrackingContext(
                correlation_id="corr-submit",
                idempotency_key="idem-p09-conflict",
            ),
        )


def test_tracking_context_is_carried_to_request_job_and_audit_payloads() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(
        _request(["SP_ANALYSIS_DOCUMENT"]),
        tracking=RequestTrackingContext(
            correlation_id="corr-p09-trace",
            idempotency_key="idem-p09-trace",
        ),
    )

    assert request_record.correlation_id == "corr-p09-trace"
    assert job.correlation_id == "corr-p09-trace"
    assert any(
        event.payload.get("tracking", {}).get("correlationId") == "corr-p09-trace"
        for event in repository.audit_events
    )


def test_repository_rejects_unsupported_job_transition() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash",
        correlation_id="corr-invalid-transition",
        idempotency_key=None,
    )
    job = repository.create_job(
        request.request_id,
        correlation_id=request.correlation_id,
    )

    with pytest.raises(WorkflowStateError, match="Unsupported job transition"):
        repository.transition_job(
            job.job_id,
            status=JobStatus.GENERATING,
            current_step=WorkflowStepType.GENERATE,
        )


def test_artifact_publish_state_blocks_validation_and_approval_mutation() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))
    artifact.status = ArtifactStatus.PUBLISHED

    with pytest.raises(WorkflowStateError, match="publish transitions are blocked"):
        service.validate_artifact(artifact.artifact_id)

    with pytest.raises(WorkflowStateError, match="publish transitions are blocked"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="REQUEST_CHANGES",
            reviewer="reviewer@example.com",
            comment="must stay draft gated",
            validation_report_id=artifact.latest_validation_report_id,
        )


def test_requested_output_placeholders_use_persisted_artifact_enums() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_request(["TABLE_COLUMN_METADATA", "DTO_MODEL_DRAFT", "DDL_DRAFT"]))

    assert {artifact.type for artifact in repository.artifacts.values()} == {
        ArtifactType.METADATA_QUERY_RESULT,
        ArtifactType.DTO_DRAFT,
        ArtifactType.VO_DRAFT,
        ArtifactType.MODEL_DRAFT,
        ArtifactType.DDL_DRAFT,
    }
    assert all("REVIEW_REQUIRED" in artifact.content for artifact in repository.artifacts.values())


def test_fixture_metadata_shapes_generation_context_and_metadata_artifact() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_fixture_request())

    metadata = next(iter(repository.metadata_collections.values()))
    assert metadata.payload["snapshotId"] == "mcp-fixture-snapshot-0001"

    contents = "\n".join(artifact.content for artifact in repository.artifacts.values())
    assert "dbo.TB_ORDER" in contents
    assert "Order identifier" in contents
    assert "OrderId" in contents


def test_approve_requires_latest_passed_validation_report() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))

    with pytest.raises(ValueError, match="PASSED"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="APPROVE",
            reviewer="reviewer@example.com",
            comment="record only",
            validation_report_id=artifact.latest_validation_report_id,
        )

    gate_report = service.evaluate_publish_gate(artifact.artifact_id)

    assert repository.artifacts[artifact.artifact_id].status.value == "REVIEW_PENDING"
    assert gate_report.status == "FAILED"
    assert gate_report.storage_result == "FAIL"
    assert gate_report.checks[0]["ruleId"] == "workflow.approval.before_publish"


def test_approve_rejects_non_latest_validation_report_id() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"]))
    artifacts = list(repository.artifacts.values())

    with pytest.raises(ValueError, match="latest artifact validation"):
        service.record_approval_decision(
            artifact_id=artifacts[0].artifact_id,
            decision="APPROVE",
            reviewer="reviewer@example.com",
            comment="wrong validation id",
            validation_report_id=artifacts[1].latest_validation_report_id,
        )


def test_request_changes_decision_maps_to_storage_rejected_without_closing_review() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))

    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="REQUEST_CHANGES",
        reviewer="reviewer@example.com",
        comment="please revise",
        validation_report_id=artifact.latest_validation_report_id,
    )

    assert approval.decision == "REQUEST_CHANGES"
    assert approval.storage_decision == "REJECTED"
    assert repository.artifacts[artifact.artifact_id].status.value == "REVIEW_PENDING"
