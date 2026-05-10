from __future__ import annotations

from api_app.repositories import (
    AgentRunRecord,
    ApprovalRecordData,
    ArtifactRecord,
    JobRecord,
    ValidationReportRecord,
)
from api_app.schemas import (
    AgentRunSummary,
    ApprovalRecord,
    Artifact,
    ArtifactSummary,
    EvidenceRef,
    Job,
    ValidationCheck,
    ValidationReport,
)


def present_job(job: JobRecord) -> Job:
    blockers = []
    caveats = []
    if job.error_code:
        blockers.append({"code": job.error_code, "message": job.error_message or job.error_code})
        caveats.append(job.error_code)
    return Job(
        jobId=job.job_id,
        requestId=job.request_id,
        status=job.status,
        currentStep=job.current_step,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        blockers=blockers,
        caveats=caveats,
        failureReason=job.error_message,
    )


def present_artifact_summary(artifact: ArtifactRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifactId=artifact.artifact_id,
        jobId=artifact.job_id,
        type=artifact.type,
        status=artifact.status,
        title=artifact.title,
        evidenceCoverage=artifact.evidence_coverage,
    )


def present_artifact(artifact: ArtifactRecord) -> Artifact:
    return Artifact(
        **present_artifact_summary(artifact).to_response(),
        content=artifact.content,
        evidenceRefs=[EvidenceRef(**ref) for ref in artifact.evidence_refs],
        generatorVersion=artifact.generator_version,
        registryRefs=list(artifact.registry_refs),
        assumptions=list(artifact.assumptions),
        reviewRequired=artifact.review_required,
    )


def present_validation_report(report: ValidationReportRecord) -> ValidationReport:
    return ValidationReport(
        validationReportId=report.validation_report_id,
        artifactId=report.artifact_id,
        status=report.status,
        checks=[ValidationCheck(**check) for check in report.checks],
        missingEvidence=report.missing_evidence,
        manualReviewPoints=report.manual_review_points,
    )


def present_agent_run(record: AgentRunRecord) -> AgentRunSummary:
    return AgentRunSummary(
        agentRunId=record.agent_run_id,
        jobId=record.job_id,
        agentType=record.agent_type,
        status=record.status,
        targetRef=record.target_ref,
        summary=record.summary,
        structuredOutput=record.structured_output,
        modelInvocation=record.model_invocation,
        createdAt=record.created_at,
    )


def present_approval_record(record: ApprovalRecordData) -> ApprovalRecord:
    return ApprovalRecord(
        approvalId=record.approval_id,
        artifactId=record.artifact_id,
        decision=record.decision,
        reviewer=record.reviewer,
        comment=record.comment,
        decidedAt=record.decided_at,
    )
