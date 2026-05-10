from __future__ import annotations

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from api_app.lifecycle import WorkflowStateError
from api_app.schemas import SPAnalysisRequest
from api_app.tracking import IdempotencyConflictError, RequestTrackingContext
from api_app.workflow import WORKFLOW_METADATA_NOTE, WorkflowService

from tests.unit.api.fake_repository import MemoryWorkflowRepository


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")


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


def _llm_request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": outputs or ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": True,
            },
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


def _passed_sp_analysis_content() -> str:
    return "\n".join(
        [
            "# Analysis",
            "",
            "## input_interpretation",
            "dbo.usp_demo",
            "",
            "## analysis_summary",
            "dbo.usp_demo is represented by metadata-only evidence.",
            "",
            "## procedure_signature",
            "dbo.usp_demo()",
            "",
            "## evidence_summary",
            "dbo.usp_demo",
            "",
            "## assumptions_and_todo",
            "None.",
            "",
            "## review_checklist",
            "- [x] Evidence refs checked.",
            "",
        ]
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
    artifact_created = [
        event for event in repository.audit_events if event.action == "ARTIFACT_CREATED"
    ]
    assert len(artifact_created) == len(repository.artifacts)
    assert all(event.payload["stage"] == "ARTIFACT" for event in artifact_created)
    assert all(event.payload["targetRef"]["type"] == "ARTIFACT" for event in artifact_created)


def test_generated_artifact_assumptions_are_deduped() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_request())

    assert repository.artifacts
    for artifact in repository.artifacts.values():
        assert len(artifact.assumptions) == len(set(artifact.assumptions))
        assert artifact.assumptions.count(WORKFLOW_METADATA_NOTE) == 1


def test_submit_with_llm_records_sanitized_agent_run_and_llm_evidence() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    _request_record, job = service.submit_sp_analysis(_llm_request())

    agent_runs = repository.list_agent_runs(job.job_id)
    assert agent_runs is not None
    assert len(agent_runs) == 1
    run = agent_runs[0]
    assert run.agent_type == "LLM_SEMANTIC_ANALYST"
    assert run.model_invocation["model"] == "gpt-5-nano"
    assert "businessRules" in run.structured_output
    assert "CREATE PROCEDURE" not in str(run.model_invocation)
    assert "CREATE PROCEDURE" not in str(run.structured_output)
    assert "CREATE PROCEDURE" not in str(repository.metadata_collections)
    assert any(
        ref["type"] == "LLM_INFERENCE"
        for artifact in repository.artifacts.values()
        for ref in artifact.evidence_refs
    )
    assert any(event.action == "AGENT_RUN_RECORDED" for event in repository.audit_events)


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
    assert all("stage" in event.payload for event in repository.audit_events)
    assert all("actor" in event.payload for event in repository.audit_events)
    assert all("targetRef" in event.payload for event in repository.audit_events)
    assert all(event.audit_id.startswith("audit_") for event in repository.audit_events)


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


def test_memory_repository_fail_job_persists_error_state_and_request_status() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-fail-job",
        correlation_id="corr-fail-job",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)

    failed = repository.fail_job(
        job.job_id,
        code="TEST_FAILURE",
        message="metadata fixture unavailable",
    )

    stored = repository.get_job(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "TEST_FAILURE"
    assert stored is not None
    assert stored.status == JobStatus.FAILED
    assert stored.error_code == "TEST_FAILURE"
    assert stored.error_message == "metadata fixture unavailable"
    assert repository.requests[request.request_id].status == JobStatus.FAILED
    audit = repository.audit_events[-1]
    assert audit.action == "JOB_FAILED"
    assert audit.payload["stage"] == "JOB"
    assert audit.payload["code"] == "TEST_FAILURE"


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


def test_approve_after_passed_validation_satisfies_gate_without_publishing() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-approve-pass",
        correlation_id="corr-approve-pass",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Passed Analysis",
        content=_passed_sp_analysis_content(),
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "dbo.usp_demo",
                "locator": "fixture.metadata",
            }
        ],
        generator_version="test",
        registry_refs=("prompt@test",),
        assumptions=(),
        review_required=False,
    )

    validation = service.validate_artifact(
        artifact.artifact_id,
        correlation_id="corr-approve-pass",
    )
    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="reviewer@example.com",
        comment="validated and approved",
        validation_report_id=validation.validation_report_id,
        correlation_id="corr-approve-pass",
    )
    gate_report = service.evaluate_publish_gate(artifact.artifact_id)

    stored = repository.artifacts[artifact.artifact_id]
    assert validation.status == "PASSED"
    assert approval.decision == "APPROVE"
    assert approval.storage_decision == "APPROVED"
    assert gate_report.status == "PASSED"
    assert gate_report.storage_result == "PASS"
    assert stored.status == ArtifactStatus.APPROVED
    assert stored.status != ArtifactStatus.PUBLISHED
    assert "PUBLISHED" not in {item.status.value for item in repository.artifacts.values()}
    assert repository.audit_events[-1].action == "PUBLISH_GATE_EVALUATED"


def test_approval_audit_payload_binds_artifact_version_refs_and_correlation() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="ppm",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "GetInspItemsCd"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-p17c-approval-audit",
        correlation_id="corr-p17c-approval-audit",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Passed P17B Analysis",
        content=_passed_sp_analysis_content(),
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "dbo.usp_demo",
                "locator": "fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml",
                "snapshotId": "live:ppm:2026-05-06T12:52:24Z",
            }
        ],
        generator_version="live-pilot-artifact-manifest-0.1.0",
        registry_refs=("fixture:live_pilot_artifacts_p17_v1",),
        assumptions=(),
        review_required=False,
        extra={
            "artifactVersion": "2026-05-06.p17b.v1",
            "selectedObjectRefs": ["PROCEDURE:dbo.GetInspItemsCd"],
        },
    )
    validation = service.validate_artifact(
        artifact.artifact_id,
        correlation_id="corr-p17c-approval-audit",
    )

    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="human.reviewer@example.com",
        comment="human approval evidence supplied outside P17C missing-template mode",
        validation_report_id=validation.validation_report_id,
        correlation_id="corr-p17c-approval-audit",
    )

    audit = [
        event
        for event in repository.audit_events
        if event.action == "APPROVAL_DECISION_RECORDED"
    ][-1]
    assert approval.decision == "APPROVE"
    assert audit.correlation_id == "corr-p17c-approval-audit"
    assert audit.payload["actor"] == "human.reviewer@example.com"
    assert audit.payload["correlationId"] == "corr-p17c-approval-audit"
    assert audit.payload["artifactId"] == artifact.artifact_id
    assert audit.payload["artifactVersion"] == "2026-05-06.p17b.v1"
    assert audit.payload["artifactRef"] == {
        "artifactId": artifact.artifact_id,
        "artifactVersion": "2026-05-06.p17b.v1",
        "artifactType": "SP_ANALYSIS_DOC",
    }
    assert audit.payload["validationRef"]["validationReportId"] == (
        validation.validation_report_id
    )
    assert audit.payload["validationRef"]["validationStatus"] == "PASSED"
    assert audit.payload["approvalRef"]["approvalId"] == approval.approval_id
    assert audit.payload["approvalRef"]["decision"] == "APPROVE"
    assert audit.payload["selectedObjectRefs"] == ["PROCEDURE:dbo.GetInspItemsCd"]
    assert audit.payload["evidenceRefs"] == artifact.evidence_refs
    assert audit.payload["refs"]["artifactVersion"] == "2026-05-06.p17b.v1"
    assert audit.payload["refs"]["validationReportId"] == validation.validation_report_id
    assert audit.payload["refs"]["approvalId"] == approval.approval_id
    assert audit.payload["timestamp"]


def test_approval_decision_requires_latest_validation_context() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-no-validation",
        correlation_id="corr-no-validation",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Analysis",
        content="# Analysis",
        evidence_refs=[],
        generator_version="test",
        registry_refs=(),
        assumptions=(),
        review_required=True,
    )

    with pytest.raises(ValueError, match="latest artifact validation"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="REQUEST_CHANGES",
            reviewer="reviewer@example.com",
            comment="needs validation first",
            validation_report_id=None,
        )


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
        validation_report_id=None,
    )

    assert approval.decision == "REQUEST_CHANGES"
    assert approval.storage_decision == "REJECTED"
    assert approval.validation_report_id == artifact.latest_validation_report_id
    assert approval.reviewer_checklist
    assert approval.validation_summary["artifactId"] == artifact.artifact_id
    assert repository.artifacts[artifact.artifact_id].status.value == "REVIEW_PENDING"
    audit = repository.audit_events[-1]
    assert audit.action == "APPROVAL_DECISION_RECORDED"
    assert audit.payload["stage"] == "APPROVAL"
    assert audit.payload["actor"] == "reviewer@example.com"
    assert audit.payload["refs"]["validationReportId"] == artifact.latest_validation_report_id
