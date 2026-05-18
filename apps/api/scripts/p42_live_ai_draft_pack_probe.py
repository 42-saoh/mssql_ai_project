#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_ROOT = REPO_ROOT / "services" / "mssql-mcp"
for import_root in (API_ROOT, MCP_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ai_agent_domain import ArtifactType, JobStatus  # noqa: E402
from ai_agent_runtime import (  # noqa: E402
    AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
    build_model_gateway_from_env,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality  # noqa: E402
from ai_agent_validation.models import ValidationStatus  # noqa: E402
from api_app.dependencies import (  # noqa: E402
    get_repository,
    get_workflow_service,
    reset_application_state,
)
from api_app.main import app  # noqa: E402
from api_app.memory_repository import MemoryWorkflowRepository  # noqa: E402
from api_app.metadata_gateway import McpMetadataGateway  # noqa: E402
from api_app.repositories import AgentRunRecord, ArtifactRecord  # noqa: E402
from api_app.workflow import OPERATION_MODEL_AGENT_TYPE, WorkflowService  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mssql_mcp_app.profiles import load_db_profiles  # noqa: E402
from mssql_mcp_app.settings import load_live_metadata_settings  # noqa: E402

LIVE_GATE_ENV = "P42_LIVE_REPLAY_GATE"
LIVE_BLOCKER = "P42_LIVE_REPLAY_REQUIRED"
LIVE_FAILED = "P42_LIVE_REPLAY_FAILED"
QUALITY_BLOCKER = "P42_LIVE_QUALITY_GATE_FAILED"
RAW_LEAKAGE_BLOCKER = "P42_LIVE_RAW_LEAKAGE_DETECTED"
TARGET = {
    "type": "PROCEDURE",
    "schema": "dbo",
    "name": "PCO_GU_ManageBond_PRC",
}
REQUIRED_ENV = (
    LIVE_GATE_ENV,
    "MSSQL_ENABLE_LIVE_METADATA",
    "MSSQL_METADATA_HOST",
    "MSSQL_METADATA_PORT",
    "MSSQL_METADATA_USER",
    "MSSQL_METADATA_PASSWORD",
    "MSSQL_METADATA_PROFILE_FILE",
    "LLM_LIVE_GATE",
    "LLM_ENABLE_REMOTE",
    "LLM_ALLOW_SP_TEXT",
    "OPENAI_API_KEY",
)
REQUIRED_DTO_CLASSES = (
    "ManageBondSearchCriteria",
    "ManageBondSearchRow",
    "ApproveAdvanceBondCommand",
    "ApproveDefectBondCommand",
    "FinanceTransferCommand",
    "CreateBondCommand",
    "CreateRetentionBondBatchItem",
    "UpdateBondCommand",
    "DeleteBondCommand",
    "VendorBondUpdateCommand",
    "OnlineBondUpdateCommand",
)
REQUIRED_METHODS = (
    "readBond",
    "approveAdvanceBond",
    "approveDefectBond",
    "sendFinanceTransfer",
    "createBond",
    "createRetentionBondBatch",
    "updateBond",
    "deleteBond",
    "updateVendorBond",
    "updateOnlineBond",
)
REQUIRED_REVIEW_MARKERS = {
    "CROSS_DB_WRITE_REVIEW_REQUIRED",
    "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
    "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
    "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
}
REDACTION = {
    "tokens": "not_returned",
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
    "rawSpDefinitions": "not_returned",
    "rawPrompts": "not_returned",
    "rawProviderResponses": "not_returned",
    "generatedSourceWrites": "not_performed",
}
FORBIDDEN_FRAGMENTS = (
    "CREATE PROCEDURE",
    "CREATE OR ALTER PROCEDURE",
    "ALTER PROCEDURE",
    "rowData",
    "row_data",
    "sampleRows",
    "sampleData",
    "procedureExecution",
    "execute stored procedure",
    "raw_prompt",
    "rawPrompt",
    "raw provider response",
    "rawProviderResponse",
    "raw_openai_response_text",
    "raw_sp_definition",
    "connectionString",
)


def run_probe(*, load_dotenv: bool = True) -> dict[str, Any]:
    if load_dotenv:
        load_root_dotenv()

    if not _flag_enabled(LIVE_GATE_ENV):
        return _result(
            status="skipped",
            blocker_code=None,
            summary=(
                "P42_LIVE_REPLAY_GATE is not enabled; default eval did not access "
                "live PPM metadata or OpenAI."
            ),
            checks=[],
            artifact_summary={},
        )

    missing = _missing_required_env()
    if missing:
        return _result(
            status="failed",
            blocker_code=LIVE_BLOCKER,
            summary="P42 live replay gate is enabled but required env names are missing.",
            checks=[
                _check(
                    "required_env",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary="Missing env name(s): " + ", ".join(missing),
                )
            ],
            artifact_summary={},
        )

    repository = MemoryWorkflowRepository()
    try:
        _require_ppm_live_profile()
        reset_application_state()
        service = WorkflowService(
            repository,
            metadata_gateway=McpMetadataGateway(),
            model_gateway=build_model_gateway_from_env(),
        )
        app.dependency_overrides[get_repository] = lambda: repository
        app.dependency_overrides[get_workflow_service] = lambda: service
        with TestClient(app) as client:
            workflow = _submit_live_workflow(client)
        artifacts = repository.list_job_artifacts(str(workflow["jobId"])) or []
        runs = repository.list_agent_runs(str(workflow["jobId"]), limit=100) or []
        artifact_summary = _verify_artifacts(artifacts)
        operation_run, ai_draft_run = _verify_agent_runs(runs)
        pack_report = _verify_persisted_pack_quality(
            artifacts,
            ai_draft_run=ai_draft_run,
        )
        for payload, check_name in (
            (workflow, "workflow_submit"),
            (artifact_summary, "artifact_inventory"),
            (_public_agent_run_summary(operation_run), "operation_model_agent_run"),
            (_public_agent_run_summary(ai_draft_run), "ai_draft_pack_agent_run"),
            (_safe_repository_payload(repository), "stored_payload_safety"),
        ):
            _assert_safe_payload(payload, check_name)
    except ProbeFailure as exc:
        return _result(
            status="failed",
            blocker_code=exc.blocker_code,
            summary=exc.summary,
            checks=exc.checks,
            artifact_summary={},
        )
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    return _result(
        status="passed",
        blocker_code=None,
        summary=(
            "P42 live AI Draft Pack replay passed with live PPM read-only metadata, "
            "remote OpenAI-compatible structured output, multi-DTO Java/MyBatis drafts, "
            "and P42 static validation."
        ),
        checks=[
            _check("metadata_profile", "pass", summary="ppm metadata profile maps to PPM."),
            _check("workflow_submit", "pass", summary=workflow["summary"]),
            _check("operation_model_agent_run", "pass", summary=operation_run.summary),
            _check("ai_draft_pack_agent_run", "pass", summary=ai_draft_run.summary),
            _check("artifact_inventory", "pass", summary=artifact_summary["summary"]),
            _check("p42_quality_gate", "pass", summary=pack_report["summary"]),
            _check(
                "stored_payload_safety",
                "pass",
                summary="Persisted payloads did not expose raw SP, prompts, row data, or secrets.",
            ),
        ],
        artifact_summary=artifact_summary,
    )


def _require_ppm_live_profile() -> None:
    settings = load_live_metadata_settings()
    if not settings.live_metadata_enabled:
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="MSSQL_ENABLE_LIVE_METADATA=1 is required.",
            checks=[
                _check("metadata_profile", "fail", blocker_code=LIVE_BLOCKER),
            ],
        )
    profiles = load_db_profiles(settings, repo_root=REPO_ROOT)
    ppm_profile = next((profile for profile in profiles if profile.id == "ppm"), None)
    if ppm_profile is None or ppm_profile.database != "PPM":
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="Metadata profile registry must include ppm -> PPM.",
            checks=[
                _check(
                    "metadata_profile",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary="No PLF fallback is allowed for the P42 PPM replay target.",
                )
            ],
        )


def _submit_live_workflow(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/requests/sp-analysis",
        headers={"X-Correlation-ID": "corr-p42g-live-replay"},
        json={
            "dbProfileId": "ppm",
            "target": TARGET,
            "outputs": ["JAVA_MYBATIS_DRAFT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": _llm_profile_id(),
                "allowSpDefinitionToModel": True,
                "sourceContextMode": "RETRIEVED_SPANS",
                "sourceDependencyMode": "NONE",
                "useAiToolOrchestration": False,
                "usePlatformToolOrchestration": False,
                "persistKnowledge": False,
            },
        },
    )
    if response.status_code != 202:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=LIVE_BLOCKER,
            check_name="workflow_submit",
        )
    payload = response.json()
    job_id = str(payload.get("jobId") or "")
    if payload.get("status") != JobStatus.VALIDATION_COMPLETE.value:
        job_payload: dict[str, Any] = {}
        if job_id:
            job_response = client.get(f"/api/v1/jobs/{job_id}")
            if job_response.status_code == 200:
                job_payload = job_response.json()
        blockers = job_payload.get("blockers") or []
        code = str(blockers[0].get("code") if blockers else LIVE_FAILED)
        raise ProbeFailure(
            blocker_code=code or LIVE_FAILED,
            summary=str(
                job_payload.get("failureReason")
                or payload.get("status")
                or "P42 live replay workflow failed."
            ),
            checks=[
                _check(
                    "workflow_submit",
                    "fail",
                    blocker_code=code or LIVE_FAILED,
                    summary="Workflow job did not reach VALIDATION_COMPLETE.",
                )
            ],
        )
    return {
        "requestId": payload.get("requestId"),
        "jobId": job_id,
        "target": TARGET,
        "summary": "Live PPM ManageBond Java/MyBatis workflow reached VALIDATION_COMPLETE.",
    }


def _verify_artifacts(artifacts: list[ArtifactRecord]) -> dict[str, Any]:
    by_type: dict[str, list[ArtifactRecord]] = {}
    for artifact in artifacts:
        by_type.setdefault(artifact.type.value, []).append(artifact)
        if not artifact.content.strip():
            raise _artifact_failure("Artifact content was blank.", artifact)
        lowered = artifact.content.lower()
        if "operationmodelreviewrequired" in lowered or "managebonddto" in lowered:
            raise _artifact_failure(
                "Fallback skeleton or single DTO collapse was detected.",
                artifact,
            )
    expected_counts = {
        ArtifactType.DTO_DRAFT.value: len(REQUIRED_DTO_CLASSES),
        ArtifactType.SERVICE_DRAFT.value: 1,
        ArtifactType.MAPPER_INTERFACE.value: 1,
        ArtifactType.MAPPER_XML.value: 1,
    }
    actual_counts = {
        artifact_type: len(by_type.get(artifact_type, []))
        for artifact_type in expected_counts
    }
    if actual_counts != expected_counts:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary=f"Unexpected artifact counts: {actual_counts}.",
            checks=[
                _check(
                    "artifact_inventory",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary=f"Expected {expected_counts}; got {actual_counts}.",
                )
            ],
        )
    dto_classes = {
        artifact.title.rsplit("/", 1)[-1].removesuffix(".java")
        for artifact in by_type[ArtifactType.DTO_DRAFT.value]
    }
    missing_dtos = sorted(set(REQUIRED_DTO_CLASSES) - dto_classes)
    extra_dtos = sorted(dto_classes - set(REQUIRED_DTO_CLASSES))
    if missing_dtos or extra_dtos:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Live P42 replay did not produce the required ManageBond DTO inventory.",
            checks=[
                _check(
                    "artifact_inventory",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary=f"Missing DTOs: {missing_dtos}; unexpected DTOs: {extra_dtos}.",
                )
            ],
        )
    service_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.SERVICE_DRAFT.value]
    )
    mapper_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.MAPPER_INTERFACE.value]
    )
    mapper_xml_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.MAPPER_XML.value]
    )
    for token in (*REQUIRED_DTO_CLASSES, *REQUIRED_METHODS):
        if token not in service_text or token not in mapper_text or token not in mapper_xml_text:
            raise ProbeFailure(
                blocker_code=QUALITY_BLOCKER,
                summary=f"Service/Mapper/XML wiring is missing token {token}.",
                checks=[
                    _check(
                        "artifact_wiring",
                        "fail",
                        blocker_code=QUALITY_BLOCKER,
                        summary=f"Missing branch/use-case DTO or method token: {token}.",
                    )
                ],
            )
    return {
        "counts": actual_counts,
        "dtoClasses": sorted(dto_classes),
        "summary": "Live replay persisted 11 DTO rows and single Service/Mapper/XML rows.",
    }


def _artifact_failure(message: str, artifact: ArtifactRecord) -> ProbeFailure:
    return ProbeFailure(
        blocker_code=QUALITY_BLOCKER,
        summary=message,
        checks=[
            _check(
                "artifact_inventory",
                "fail",
                blocker_code=QUALITY_BLOCKER,
                summary=f"{artifact.type.value} {artifact.title}: {message}",
            )
        ],
    )


def _verify_agent_runs(
    runs: list[AgentRunRecord],
) -> tuple[AgentRunRecord, AgentRunRecord]:
    operation_run = next(
        (run for run in runs if run.agent_type == OPERATION_MODEL_AGENT_TYPE),
        None,
    )
    ai_draft_run = next(
        (run for run in runs if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE),
        None,
    )
    if operation_run is None or ai_draft_run is None:
        raise ProbeFailure(
            blocker_code=LIVE_FAILED,
            summary="Expected operation-model and AI Draft Pack agent runs were not recorded.",
            checks=[
                _check(
                    "agent_runs",
                    "fail",
                    blocker_code=LIVE_FAILED,
                    summary=f"Recorded agent types: {[run.agent_type for run in runs]}",
                )
            ],
        )
    if operation_run.status != "SUCCEEDED" or ai_draft_run.status != "SUCCEEDED":
        raise ProbeFailure(
            blocker_code=LIVE_FAILED,
            summary="Expected live planner agent runs to succeed.",
            checks=[
                _check(
                    "agent_runs",
                    "fail",
                    blocker_code=LIVE_FAILED,
                    summary=(
                        f"Operation status={operation_run.status}; "
                        f"AI draft status={ai_draft_run.status}."
                    ),
                )
            ],
        )
    return operation_run, ai_draft_run


def _verify_persisted_pack_quality(
    artifacts: list[ArtifactRecord],
    *,
    ai_draft_run: AgentRunRecord,
) -> dict[str, Any]:
    pack = _pack_from_persisted_artifacts(artifacts, ai_draft_run=ai_draft_run)
    report = validate_ai_java_mybatis_draft_pack_quality(pack)
    if report.status != ValidationStatus.PASSED:
        failed = [
            check.message
            for check in report.checks
            if check.result.value == "FAIL"
        ][:10]
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Persisted live artifacts failed the P42 static quality validator.",
            checks=[
                _check(
                    "p42_quality_gate",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary="; ".join(failed),
                )
            ],
        )
    missing_markers = REQUIRED_REVIEW_MARKERS - set(report.manual_review_points)
    if missing_markers:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Persisted live artifacts lost required REVIEW_REQUIRED markers.",
            checks=[
                _check(
                    "p42_quality_gate",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary="Missing marker(s): " + ", ".join(sorted(missing_markers)),
                )
            ],
        )
    return {
        "summary": "Persisted artifacts reconstruct to a valid AiJavaMyBatisDraftPack.v0.1.",
        "manualReviewPoints": sorted(report.manual_review_points),
        "scores": dict(report.metadata.get("scores") or {}),
    }


def _pack_from_persisted_artifacts(
    artifacts: list[ArtifactRecord],
    *,
    ai_draft_run: AgentRunRecord,
) -> dict[str, Any]:
    source_pack = dict(ai_draft_run.structured_output)
    source_files = {
        str(file.get("path")): dict(file)
        for file in source_pack.get("files", [])
        if isinstance(file, Mapping) and file.get("path")
    }
    files: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.type not in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }:
            continue
        path = str(artifact.extra.get("bundleFilePath") or artifact.title)
        source_file = source_files.get(path)
        if source_file is None:
            raise ProbeFailure(
                blocker_code=QUALITY_BLOCKER,
                summary=f"Persisted artifact path not found in AI Draft Pack: {path}.",
                checks=[
                    _check("p42_quality_gate", "fail", blocker_code=QUALITY_BLOCKER)
                ],
            )
        payload = {
            "artifactType": artifact.type.value,
            "path": path,
            "role": artifact.extra.get("aiFileRole") or source_file.get("role"),
            "className": source_file.get("className"),
            "content": artifact.content,
            "operationIds": list(artifact.extra.get("operationIds") or []),
            "evidenceRefs": list(artifact.extra.get("aiEvidenceRefs") or []),
            "reviewMarkers": list(artifact.extra.get("reviewMarkers") or []),
        }
        for optional_key in ("dtoRole", "requiredFields", "references", "qualityScore"):
            value = artifact.extra.get(optional_key)
            if value is None:
                value = source_file.get(optional_key)
            if value is not None:
                payload[optional_key] = value
        files.append(payload)
    return {
        "schemaVersion": source_pack.get("schemaVersion"),
        "contractTarget": source_pack.get("contractTarget"),
        "targetRef": source_pack.get("targetRef"),
        "sourcePolicy": source_pack.get("sourcePolicy"),
        "productionReady": source_pack.get("productionReady"),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "evidenceRefs": list(source_pack.get("evidenceRefs") or []),
        "reviewMarkers": list(source_pack.get("reviewMarkers") or []),
        "qualityGates": dict(source_pack.get("qualityGates") or {}),
        "assumptions": list(source_pack.get("assumptions") or []),
    }


def _safe_repository_payload(repository: MemoryWorkflowRepository) -> dict[str, Any]:
    return {
        "metadataCollections": [
            record.payload for record in repository.metadata_collections.values()
        ],
        "agentRuns": [
            {
                "agentType": run.agent_type,
                "status": run.status,
                "summary": run.summary,
                "structuredOutput": run.structured_output,
                "modelInvocation": run.model_invocation,
            }
            for run in repository.agent_runs.values()
        ],
        "artifacts": [
            {
                "type": artifact.type.value,
                "title": artifact.title,
                "content": artifact.content,
                "extra": artifact.extra,
                "evidenceRefs": artifact.evidence_refs,
            }
            for artifact in repository.artifacts.values()
        ],
        "auditEvents": [event.payload for event in repository.audit_events],
    }


def _public_agent_run_summary(run: AgentRunRecord) -> dict[str, Any]:
    invocation = dict(run.model_invocation or {})
    return {
        "agentType": run.agent_type,
        "status": run.status,
        "targetRef": run.target_ref,
        "provider": invocation.get("provider"),
        "model": invocation.get("model"),
        "promptVersion": invocation.get("promptVersion"),
        "outputSchemaVersion": invocation.get("outputSchemaVersion"),
        "statusSummary": invocation.get("status"),
    }


class ProbeFailure(RuntimeError):
    def __init__(
        self,
        *,
        blocker_code: str,
        summary: str,
        checks: list[dict[str, Any]],
    ) -> None:
        super().__init__(summary)
        self.blocker_code = blocker_code
        self.summary = summary
        self.checks = checks

    @classmethod
    def from_response(
        cls,
        response: Any,
        *,
        fallback_blocker: str,
        check_name: str,
    ) -> ProbeFailure:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        code = str(payload.get("code") or fallback_blocker)
        detail = str(payload.get("detail") or f"HTTP {response.status_code}")
        return cls(
            blocker_code=code,
            summary=detail,
            checks=[
                _check(
                    check_name,
                    "fail",
                    blocker_code=code,
                    summary=f"HTTP {response.status_code}: {detail}",
                )
            ],
        )


def _assert_safe_payload(payload: Any, check_name: str) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    lowered = serialized.lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        if fragment.lower() in lowered:
            raise ProbeFailure(
                blocker_code=RAW_LEAKAGE_BLOCKER,
                summary="P42 live replay detected forbidden raw payload text.",
                checks=[
                    _check(
                        check_name,
                        "fail",
                        blocker_code=RAW_LEAKAGE_BLOCKER,
                        summary=f"Forbidden fragment category detected: {fragment}",
                    )
                ],
            )
    for label, value in {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "MSSQL_METADATA_PASSWORD": os.getenv("MSSQL_METADATA_PASSWORD", ""),
    }.items():
        secret = value.strip()
        if len(secret) >= 8 and secret in serialized:
            raise ProbeFailure(
                blocker_code=RAW_LEAKAGE_BLOCKER,
                summary="P42 live replay detected a secret value in persisted output.",
                checks=[
                    _check(
                        check_name,
                        "fail",
                        blocker_code=RAW_LEAKAGE_BLOCKER,
                        summary=f"Secret category detected: {label}",
                    )
                ],
            )


def _result(
    *,
    status: str,
    blocker_code: str | None,
    summary: str,
    checks: list[dict[str, Any]],
    artifact_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate": LIVE_GATE_ENV,
        "status": status,
        "productionReady": False,
        "blockerCode": blocker_code,
        "summary": summary,
        "target": TARGET,
        "checks": checks,
        "artifactSummary": artifact_summary,
        "redaction": REDACTION,
    }


def _check(
    name: str,
    status: str,
    *,
    blocker_code: str | None = None,
    summary: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "blockerCode": blocker_code,
        "summary": summary,
    }


def _missing_required_env() -> list[str]:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name, "").strip()]
    for enabled_name in (
        LIVE_GATE_ENV,
        "MSSQL_ENABLE_LIVE_METADATA",
        "LLM_LIVE_GATE",
        "LLM_ENABLE_REMOTE",
        "LLM_ALLOW_SP_TEXT",
    ):
        if os.getenv(enabled_name, "").strip() != "1":
            missing.append(f"{enabled_name}=1")
    if _remote_provider() == "pgpt" and not (
        os.getenv("OPENAI_RESPONSES_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
    ):
        missing.append("OPENAI_BASE_URL or OPENAI_RESPONSES_URL")
    return sorted(dict.fromkeys(missing))


def _llm_profile_id() -> str:
    value = os.getenv("P42_LIVE_LLM_PROFILE_ID", "openai_sp_semantic_analysis").strip()
    if value in {"openai_sp_semantic_analysis", "openai_fast_test"}:
        return value
    return "openai_sp_semantic_analysis"


def _remote_provider() -> str:
    provider = os.getenv("LLM_REMOTE_PROVIDER", "openai").strip().lower()
    if provider in {"pgpt", "p-gpt", "private-gpt"}:
        return "pgpt"
    return "openai"


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_root_dotenv(path: Path | None = None) -> None:
    env_path = path or REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    result = run_probe(load_dotenv=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
