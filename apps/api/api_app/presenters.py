from __future__ import annotations

from ai_agent_domain import RequestedOutputType

from api_app.repositories import (
    AgentRunRecord,
    ArtifactRecord,
    JobRecord,
    ValidationReportRecord,
)
from api_app.schemas import (
    AgentRunSummary,
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
        dbProfileId=job.db_profile_id,
        target=_present_target(job.target),
        targetKey=job.target_key,
        outputs=_present_outputs(job.outputs),
        currentStep=job.current_step,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        blockers=blockers,
        caveats=caveats,
        failureReason=job.error_message,
    )


def _present_target(target: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(target, dict):
        return None
    target_type = str(target.get("type") or "").strip().upper()
    schema = str(target.get("schema") or "").strip()
    name = str(target.get("name") or "").strip()
    if target_type not in {"PROCEDURE", "TABLE", "VIEW", "FUNCTION"} or not schema or not name:
        return None
    return {"type": target_type, "schema": schema, "name": name}


def _present_outputs(outputs: tuple[str, ...]) -> list[str]:
    allowed = {item.value for item in RequestedOutputType}
    return [output for output in outputs if output in allowed]

def present_artifact_summary(artifact: ArtifactRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifactId=artifact.artifact_id,
        jobId=artifact.job_id,
        type=artifact.type,
        status=artifact.status,
        title=artifact.title,
        targetKey=artifact.target_key,
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
        qualityCaveats=report.manual_review_points,
    )


def present_agent_run(record: AgentRunRecord) -> AgentRunSummary:
    return AgentRunSummary(
        agentRunId=record.agent_run_id,
        jobId=record.job_id,
        agentType=record.agent_type,
        status=record.status,
        targetRef=record.target_ref,
        targetKey=record.target_key,
        summary=record.summary,
        structuredOutput=record.structured_output,
        modelInvocation=record.model_invocation,
        createdAt=record.created_at,
    )
