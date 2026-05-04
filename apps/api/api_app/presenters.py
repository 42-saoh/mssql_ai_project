from __future__ import annotations

from api_app.repositories import (
    ApprovalRecordData,
    ArtifactRecord,
    JobRecord,
    ValidationReportRecord,
)
from api_app.schemas import (
    ApprovalRecord,
    Artifact,
    ArtifactSummary,
    EvidenceRef,
    Job,
    ValidationCheck,
    ValidationReport,
)


def present_job(job: JobRecord) -> Job:
    return Job(
        jobId=job.job_id,
        requestId=job.request_id,
        status=job.status,
        currentStep=job.current_step,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
    )


def present_artifact_summary(artifact: ArtifactRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifactId=artifact.artifact_id,
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
        artifactId=report.artifact_id,
        status=report.status,
        checks=[ValidationCheck(**check) for check in report.checks],
        missingEvidence=report.missing_evidence,
        manualReviewPoints=report.manual_review_points,
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
