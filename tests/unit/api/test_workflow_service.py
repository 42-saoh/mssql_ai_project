from __future__ import annotations

from ai_agent_domain import ArtifactType, JobStatus
from api_app.schemas import SPAnalysisRequest
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


def test_publish_gate_fails_without_passed_validation_even_after_approval() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))

    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="reviewer@example.com",
        comment="record only",
        validation_report_id=artifact.latest_validation_report_id,
    )
    gate_report = service.evaluate_publish_gate(artifact.artifact_id)

    assert approval.decision == "APPROVE"
    assert approval.storage_decision == "APPROVED"
    assert gate_report.status == "FAILED"
    assert gate_report.storage_result == "FAIL"
    assert gate_report.checks[0]["ruleId"] == "workflow.approval.before_publish"


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
