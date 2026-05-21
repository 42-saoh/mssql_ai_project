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
    AiDraftPackValidationError,
    build_ai_java_mybatis_draft_pack_run,
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
LIVE_MODE_ENV = "P42_LIVE_REPLAY_MODE"
LIVE_MODE_LIVE_PPM = "live_ppm"
LIVE_MODE_SANITIZED_FIXTURE = "sanitized_fixture"
LIVE_BLOCKER = "P42_LIVE_REPLAY_REQUIRED"
LIVE_FAILED = "P42_LIVE_REPLAY_FAILED"
QUALITY_BLOCKER = "P42_LIVE_QUALITY_GATE_FAILED"
RAW_LEAKAGE_BLOCKER = "P42_LIVE_RAW_LEAKAGE_DETECTED"
TARGET = {
    "type": "PROCEDURE",
    "schema": "dbo",
    "name": "PCO_GU_ManageBond_PRC",
}
JAVA_PACKAGE_CONTEXT = {
    "modelPackage": "com.pec.ppm.workflow.draft.model",
    "servicePackage": "com.pec.ppm.workflow.draft.service",
    "mapperPackage": "com.pec.ppm.workflow.draft.mapper",
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
SANITIZED_FIXTURE_REQUIRED_ENV = (
    LIVE_GATE_ENV,
    "LLM_LIVE_GATE",
    "LLM_ENABLE_REMOTE",
    "OPENAI_API_KEY",
)
GENERIC_FALLBACK_BLOCKER_PATTERNS = (
    "OperationModelReviewRequired",
    "P41_OPERATION_MODEL_REVIEW_REQUIRED",
)
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
POLICY_ONLY_SCAN_SKIP_KEYS = frozenset(
    {
        "blockerPatterns",
        "forbiddenPayloadFields",
        "forbiddenRuntimeActions",
        "forbidden_payload_fields",
        "forbidden_runtime_actions",
        "redaction",
    }
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
            diagnostics={},
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
            diagnostics={},
        )

    if _live_replay_mode() == LIVE_MODE_SANITIZED_FIXTURE:
        return _run_sanitized_fixture_live_replay()

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
            workflow = _submit_live_workflow(client, repository)
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
            diagnostics=exc.diagnostics,
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
        diagnostics={},
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


def _run_sanitized_fixture_live_replay() -> dict[str, Any]:
    try:
        fixture = _load_ai_draft_pack_fixture()
        target = fixture["ai_draft_pack_quality_target"]
        quality_gates = _fixture_quality_gates(fixture)
        expected_inventory = list(target["expectedFiles"])
        allowed_refs = _fixture_allowed_refs(target)
        context = _fixture_sanitized_context(fixture)
        run = build_ai_java_mybatis_draft_pack_run(
            target_ref=str(target["targetRef"]),
            sanitized_draft_context=context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=build_model_gateway_from_env(),
            profile_id=_llm_profile_id(default="openai_ai_draft_pack"),
            allowed_evidence_refs=allowed_refs,
        )
        pack = dict(run.structured_output)
        artifact_summary = _verify_pack_output(pack)
        pack_report = _verify_pack_quality(pack)
        for payload, check_name in (
            (pack, "sanitized_fixture_pack"),
            (run.model_invocation.to_storage_dict(), "sanitized_fixture_invocation"),
        ):
            _assert_safe_payload(payload, check_name)
    except ProbeFailure as exc:
        return _result(
            status="failed",
            blocker_code=exc.blocker_code,
            summary=exc.summary,
            checks=exc.checks,
            artifact_summary={},
            diagnostics=exc.diagnostics,
        )
    except AiDraftPackValidationError as exc:
        findings = [str(item) for item in exc.findings[:10]]
        return _result(
            status="failed",
            blocker_code=LIVE_FAILED,
            summary="P42 sanitized fixture live replay failed draft-pack schema validation.",
            checks=[
                _check(
                    "sanitized_fixture_live_replay",
                    "fail",
                    blocker_code=LIVE_FAILED,
                    summary="; ".join(findings),
                )
            ],
            artifact_summary={},
            diagnostics={
                "failureStage": "sanitized_fixture_live_replay",
                "errorCode": LIVE_FAILED,
                "errorClass": exc.__class__.__name__,
                "validationFindingCount": len(exc.findings),
                "validationFindings": findings,
            },
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must stay sanitized
        return _result(
            status="failed",
            blocker_code=LIVE_FAILED,
            summary="P42 sanitized fixture live replay failed before deterministic scoring.",
            checks=[
                _check(
                    "sanitized_fixture_live_replay",
                    "fail",
                    blocker_code=LIVE_FAILED,
                    summary=f"errorClass={exc.__class__.__name__}",
                )
            ],
            artifact_summary={},
            diagnostics={
                "failureStage": "sanitized_fixture_live_replay",
                "errorCode": LIVE_FAILED,
                "errorClass": exc.__class__.__name__,
            },
        )
    return _result(
        status="passed",
        blocker_code=None,
        summary=(
            "P42 sanitized fixture live AI Draft Pack replay passed without live PPM "
            "metadata, raw SP text, row data, or procedure execution."
        ),
        checks=[
            _check(
                "sanitized_fixture_context",
                "pass",
                summary="Used sanitized fixture facts only; raw SP external export was not required.",
            ),
            _check("ai_draft_pack_agent_run", "pass", summary=run.summary),
            _check("artifact_inventory", "pass", summary=artifact_summary["summary"]),
            _check("p42_quality_gate", "pass", summary=pack_report["summary"]),
            _check(
                "stored_payload_safety",
                "pass",
                summary="Live fixture replay output did not expose raw SP, prompts, row data, or secrets.",
            ),
        ],
        artifact_summary=artifact_summary,
        diagnostics={},
    )


def _load_ai_draft_pack_fixture() -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # noqa: BLE001
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="PyYAML is required for sanitized fixture live replay.",
            checks=[
                _check(
                    "sanitized_fixture_context",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary=f"errorClass={exc.__class__.__name__}",
                )
            ],
        ) from None
    path = REPO_ROOT / "fixtures" / "eval" / "ai_draft_pack_p42_manage_bond_v1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _benchmark_quality_gates() -> dict[str, Any]:
    return _fixture_quality_gates(_load_ai_draft_pack_fixture())


def _benchmark_dto_signals() -> set[str]:
    return set(_benchmark_quality_gates()["requiredDtoClasses"])


def _required_review_markers() -> set[str]:
    return set(_benchmark_quality_gates()["requiredReviewMarkers"])


def _blocker_patterns() -> tuple[str, ...]:
    gates = _benchmark_quality_gates()
    patterns = [
        *GENERIC_FALLBACK_BLOCKER_PATTERNS,
        *[str(item) for item in gates.get("blockerPatterns", [])],
    ]
    return tuple(dict.fromkeys(pattern for pattern in patterns if pattern.strip()))


def _contains_blocker_pattern(value: str, patterns: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _fixture_quality_gates(fixture: Mapping[str, Any]) -> dict[str, Any]:
    target = fixture["ai_draft_pack_quality_target"]
    gates = fixture["quality_gates"]
    return {
        "requiredDtoClasses": list(gates["required_dto_classes"]),
        "requiredServiceMethods": list(gates["required_service_methods"]),
        "requiredMapperMethods": list(gates["required_mapper_methods"]),
        "requiredReviewMarkers": list(target["reviewMarkers"]),
        "blockerPatterns": list(gates["blocker_patterns"]),
        "blankContentIsBlocker": bool(gates["blank_content_is_blocker"]),
        "dtoCollapseIsBlocker": bool(gates["dto_collapse_is_blocker"]),
        "fallbackSkeletonPersistenceAllowedOnFailure": bool(
            gates["fallback_skeleton_persistence_allowed_on_failure"]
        ),
    }


def _fixture_allowed_refs(target: Mapping[str, Any]) -> list[str]:
    refs = list(target.get("evidenceRefs", []))
    for item in target.get("expectedFiles", []):
        if isinstance(item, Mapping):
            refs.extend(item.get("evidenceRefs", []))
    return sorted(dict.fromkeys(str(ref) for ref in refs if str(ref).strip()))


def _fixture_sanitized_context(fixture: Mapping[str, Any]) -> dict[str, Any]:
    facts = fixture["guide_quality_facts"]
    return {
        "targetRef": facts["target_ref"],
        "branchVariables": list(facts["branch_variables"]),
        "reviewRequiredFacts": list(facts["review_required_facts"]),
        "javaPackageContext": dict(JAVA_PACKAGE_CONTEXT),
        "dependencyEvidenceSummary": {
            "sameDatabaseCount": len(facts["major_dependencies"]["same_database"]),
            "crossDatabaseCount": len(facts["major_dependencies"]["cross_database"]),
            "calledProcedureCount": len(facts["major_dependencies"]["called_procedures"]),
            "evidenceRefs": list(
                fixture["ai_draft_pack_quality_target"].get("evidenceRefs", [])
            ),
        },
    }


def _submit_live_workflow(
    client: TestClient,
    repository: MemoryWorkflowRepository,
) -> dict[str, Any]:
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
        diagnostics = _failure_diagnostics(repository, job_id)
        checks = [
            _check(
                "workflow_submit",
                "fail",
                blocker_code=code or LIVE_FAILED,
                summary="Workflow job did not reach VALIDATION_COMPLETE.",
            )
        ]
        if diagnostics:
            checks.append(
                _check(
                    "planner_failure_diagnostics",
                    "fail",
                    blocker_code=code or LIVE_FAILED,
                    summary=_diagnostics_summary(diagnostics),
                )
            )
        raise ProbeFailure(
            blocker_code=code or LIVE_FAILED,
            summary=str(
                job_payload.get("failureReason")
                or payload.get("status")
                or "P42 live replay workflow failed."
            ),
            checks=checks,
            diagnostics=diagnostics,
        )
    return {
        "requestId": payload.get("requestId"),
        "jobId": job_id,
        "target": TARGET,
        "summary": "Live PPM ManageBond Java/MyBatis workflow reached VALIDATION_COMPLETE.",
    }


def _verify_artifacts(artifacts: list[ArtifactRecord]) -> dict[str, Any]:
    by_type: dict[str, list[ArtifactRecord]] = {}
    blocker_patterns = _blocker_patterns()
    for artifact in artifacts:
        by_type.setdefault(artifact.type.value, []).append(artifact)
        if not artifact.content.strip():
            raise _artifact_failure("Artifact content was blank.", artifact)
        if _contains_blocker_pattern(artifact.content, blocker_patterns):
            raise _artifact_failure(
                "Fallback skeleton or single DTO collapse was detected.",
                artifact,
            )
    actual_counts = {
        ArtifactType.DTO_DRAFT.value: len(by_type.get(ArtifactType.DTO_DRAFT.value, [])),
        ArtifactType.SERVICE_DRAFT.value: len(by_type.get(ArtifactType.SERVICE_DRAFT.value, [])),
        ArtifactType.MAPPER_INTERFACE.value: len(
            by_type.get(ArtifactType.MAPPER_INTERFACE.value, [])
        ),
        ArtifactType.MAPPER_XML.value: len(by_type.get(ArtifactType.MAPPER_XML.value, [])),
    }
    count_failures: list[str] = []
    for artifact_type in (
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    ):
        if actual_counts[artifact_type] != 1:
            count_failures.append(
                f"{artifact_type} expected exactly 1, got {actual_counts[artifact_type]}"
            )
    if actual_counts[ArtifactType.DTO_DRAFT.value] < 3:
        count_failures.append(
            f"DTO_DRAFT expected at least 3, got {actual_counts[ArtifactType.DTO_DRAFT.value]}"
        )
    if count_failures:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary=f"Unexpected artifact counts: {actual_counts}.",
            checks=[
                _check(
                    "artifact_inventory",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary="; ".join(count_failures),
                )
            ],
        )
    dto_classes = {
        artifact.title.rsplit("/", 1)[-1].removesuffix(".java")
        for artifact in by_type[ArtifactType.DTO_DRAFT.value]
    }
    collapsed_dtos = sorted(
        dto
        for dto in dto_classes
        if _contains_blocker_pattern(dto, blocker_patterns)
    )
    if collapsed_dtos:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Live P42 replay produced collapsed or fallback DTO classes.",
            checks=[
                _check(
                    "artifact_inventory",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary=f"Collapsed/fallback DTO classes: {collapsed_dtos}.",
                )
            ],
        )
    benchmark_dto_signals = _benchmark_dto_signals()
    benchmark_missing = sorted(benchmark_dto_signals - dto_classes)
    benchmark_matched = sorted(benchmark_dto_signals & dto_classes)
    additional_dtos = sorted(dto_classes - benchmark_dto_signals)
    service_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.SERVICE_DRAFT.value]
    )
    mapper_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.MAPPER_INTERFACE.value]
    )
    mapper_xml_text = "\n".join(
        artifact.content for artifact in by_type[ArtifactType.MAPPER_XML.value]
    )
    non_dto_operation_ids: set[str] = set()
    for artifact_type in (
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    ):
        for artifact in by_type[artifact_type]:
            non_dto_operation_ids.update(
                str(operation_id)
                for operation_id in artifact.extra.get("operationIds", [])
                if str(operation_id).strip()
            )
    for token in (*sorted(dto_classes), *sorted(non_dto_operation_ids)):
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
        "benchmark": {
            "target": "PPM.dbo.PCO_GU_ManageBond_PRC",
            "role": "quality_signal_only_not_runtime_answer_key",
            "expectedDtoSignalCount": len(benchmark_dto_signals),
            "matchedDtoSignals": benchmark_matched,
            "missingDtoSignals": benchmark_missing,
        },
        "additionalDtoClasses": additional_dtos,
        "summary": (
            "Live replay persisted split DTOs and single Service/Mapper/XML rows; "
            "named ManageBond DTOs are reported as benchmark signals only."
        ),
    }


def _verify_pack_output(pack: Mapping[str, Any]) -> dict[str, Any]:
    files = [file for file in pack.get("files", []) if isinstance(file, Mapping)]
    by_type: dict[str, list[Mapping[str, Any]]] = {}
    blocker_patterns = _blocker_patterns()
    for file in files:
        artifact_type = str(file.get("artifactType") or "")
        by_type.setdefault(artifact_type, []).append(file)
        if not str(file.get("content") or "").strip():
            raise ProbeFailure(
                blocker_code=QUALITY_BLOCKER,
                summary="Sanitized live replay produced blank draft content.",
                checks=[
                    _check(
                        "artifact_inventory",
                        "fail",
                        blocker_code=QUALITY_BLOCKER,
                        summary=f"Blank content in {artifact_type} {file.get('path')}.",
                    )
                ],
            )
        content = str(file.get("content") or "")
        class_name = str(file.get("className") or "")
        if _contains_blocker_pattern(content, blocker_patterns) or _contains_blocker_pattern(
            class_name,
            blocker_patterns,
        ):
            raise ProbeFailure(
                blocker_code=QUALITY_BLOCKER,
                summary="Sanitized live replay produced fallback or collapsed DTO content.",
                checks=[
                    _check(
                        "artifact_inventory",
                        "fail",
                        blocker_code=QUALITY_BLOCKER,
                        summary=f"Fallback/collapse marker in {artifact_type} {file.get('path')}.",
                    )
                ],
            )
    actual_counts = {
        ArtifactType.DTO_DRAFT.value: len(by_type.get(ArtifactType.DTO_DRAFT.value, [])),
        ArtifactType.SERVICE_DRAFT.value: len(by_type.get(ArtifactType.SERVICE_DRAFT.value, [])),
        ArtifactType.MAPPER_INTERFACE.value: len(
            by_type.get(ArtifactType.MAPPER_INTERFACE.value, [])
        ),
        ArtifactType.MAPPER_XML.value: len(by_type.get(ArtifactType.MAPPER_XML.value, [])),
    }
    count_failures = [
        f"{artifact_type} expected exactly 1, got {actual_counts[artifact_type]}"
        for artifact_type in (
            ArtifactType.SERVICE_DRAFT.value,
            ArtifactType.MAPPER_INTERFACE.value,
            ArtifactType.MAPPER_XML.value,
        )
        if actual_counts[artifact_type] != 1
    ]
    if actual_counts[ArtifactType.DTO_DRAFT.value] < 3:
        count_failures.append(
            f"DTO_DRAFT expected at least 3, got {actual_counts[ArtifactType.DTO_DRAFT.value]}"
        )
    if count_failures:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary=f"Unexpected sanitized fixture live artifact counts: {actual_counts}.",
            checks=[
                _check(
                    "artifact_inventory",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary="; ".join(count_failures),
                )
            ],
        )
    dto_classes = {
        str(file.get("className") or "")
        for file in by_type.get(ArtifactType.DTO_DRAFT.value, [])
        if str(file.get("className") or "").strip()
    }
    benchmark_dto_signals = _benchmark_dto_signals()
    benchmark_missing = sorted(benchmark_dto_signals - dto_classes)
    benchmark_matched = sorted(benchmark_dto_signals & dto_classes)
    return {
        "counts": actual_counts,
        "dtoClasses": sorted(dto_classes),
        "benchmark": {
            "target": "PPM.dbo.PCO_GU_ManageBond_PRC",
            "role": "quality_signal_only_not_runtime_answer_key",
            "expectedDtoSignalCount": len(benchmark_dto_signals),
            "matchedDtoSignals": benchmark_matched,
            "missingDtoSignals": benchmark_missing,
        },
        "summary": (
            "Sanitized fixture live replay produced split DTOs and single "
            "Service/Mapper/XML rows; benchmark DTOs are metrics only."
        ),
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
    missing_markers = _required_review_markers() - set(report.manual_review_points)
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


def _verify_pack_quality(pack: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_ai_java_mybatis_draft_pack_quality(dict(pack))
    if report.status != ValidationStatus.PASSED:
        failed = [
            check.message
            for check in report.checks
            if check.result.value == "FAIL"
        ][:10]
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Sanitized fixture live AI Draft Pack failed the P42 static validator.",
            checks=[
                _check(
                    "p42_quality_gate",
                    "fail",
                    blocker_code=QUALITY_BLOCKER,
                    summary="; ".join(failed),
                )
            ],
        )
    missing_markers = _required_review_markers() - set(report.manual_review_points)
    if missing_markers:
        raise ProbeFailure(
            blocker_code=QUALITY_BLOCKER,
            summary="Sanitized fixture live output lost required REVIEW_REQUIRED markers.",
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
        "summary": "Sanitized fixture live output passed the P42 static validator.",
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


def _failure_diagnostics(
    repository: MemoryWorkflowRepository,
    job_id: str,
) -> dict[str, Any]:
    if not job_id:
        return {}
    runs = repository.list_agent_runs(job_id, limit=100) or []
    operation_run = next(
        (run for run in runs if run.agent_type == OPERATION_MODEL_AGENT_TYPE),
        None,
    )
    ai_draft_run = next(
        (run for run in runs if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE),
        None,
    )
    if operation_run is None and ai_draft_run is None:
        return {}
    return {
        "operationModel": _agent_run_failure_summary(operation_run),
        "aiDraftPack": _agent_run_failure_summary(ai_draft_run),
    }


def _diagnostics_summary(diagnostics: Mapping[str, Any]) -> str:
    for key in ("operationModel", "aiDraftPack"):
        summary = diagnostics.get(key)
        if not isinstance(summary, Mapping):
            continue
        failure = summary.get("failureDiagnostics")
        if isinstance(failure, Mapping):
            stage = failure.get("failureStage") or key
            code = failure.get("errorCode") or "unknown"
            error_class = failure.get("errorClass") or ""
            return f"{key}:{stage}:{code}:{error_class}".rstrip(":")
    return "AI Draft Pack failure diagnostics were recorded."


def _agent_run_failure_summary(run: AgentRunRecord | None) -> dict[str, Any]:
    if run is None:
        return {}
    structured_output = dict(run.structured_output or {})
    invocation = dict(run.model_invocation or {})
    component_invocations = invocation.get("componentInvocations") or []
    diagnostics = structured_output.get("failureDiagnostics")
    if not isinstance(diagnostics, Mapping):
        diagnostics = _failure_diagnostics_from_components(component_invocations)
    return {
        "agentType": run.agent_type,
        "status": run.status,
        "summary": run.summary,
        "targetRef": run.target_ref,
        "failureDiagnostics": diagnostics if isinstance(diagnostics, Mapping) else {},
        "modelInvocation": {
            "provider": invocation.get("provider"),
            "model": invocation.get("model"),
            "promptVersion": invocation.get("promptVersion"),
            "outputSchemaVersion": invocation.get("outputSchemaVersion"),
            "status": invocation.get("status"),
            "componentInvocations": component_invocations,
        },
    }


def _failure_diagnostics_from_components(components: Any) -> dict[str, Any]:
    if not isinstance(components, (list, tuple)):
        return {}
    for component in components:
        if not isinstance(component, Mapping):
            continue
        diagnostics = component.get("failureDiagnostics")
        if isinstance(diagnostics, Mapping):
            return dict(diagnostics)
        reason = component.get("reason")
        if isinstance(reason, str) and reason.strip():
            return {
                "failureStage": str(component.get("component") or "workflow_gate"),
                "errorCode": reason.strip(),
                "errorClass": str(component.get("errorClass") or ""),
            }
    return {}


class ProbeFailure(RuntimeError):
    def __init__(
        self,
        *,
        blocker_code: str,
        summary: str,
        checks: list[dict[str, Any]],
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(summary)
        self.blocker_code = blocker_code
        self.summary = summary
        self.checks = checks
        self.diagnostics = diagnostics or {}

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
            diagnostics={},
        )


def _assert_safe_payload(payload: Any, check_name: str) -> None:
    serialized = json.dumps(
        _payload_for_leakage_scan(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
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


def _payload_for_leakage_scan(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text in POLICY_ONLY_SCAN_SKIP_KEYS:
                continue
            cleaned[key_text] = _payload_for_leakage_scan(value)
        return cleaned
    if isinstance(payload, list | tuple):
        return [_payload_for_leakage_scan(item) for item in payload]
    return payload


def _result(
    *,
    status: str,
    blocker_code: str | None,
    summary: str,
    checks: list[dict[str, Any]],
    artifact_summary: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate": LIVE_GATE_ENV,
        "mode": _live_replay_mode(),
        "status": status,
        "productionReady": False,
        "blockerCode": blocker_code,
        "summary": summary,
        "target": TARGET,
        "checks": checks,
        "artifactSummary": artifact_summary,
        "diagnostics": diagnostics,
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
    mode = _live_replay_mode()
    required = (
        SANITIZED_FIXTURE_REQUIRED_ENV
        if mode == LIVE_MODE_SANITIZED_FIXTURE
        else REQUIRED_ENV
    )
    missing = [name for name in required if not os.getenv(name, "").strip()]
    enabled_names = [LIVE_GATE_ENV, "LLM_LIVE_GATE", "LLM_ENABLE_REMOTE"]
    if mode != LIVE_MODE_SANITIZED_FIXTURE:
        enabled_names.extend(("MSSQL_ENABLE_LIVE_METADATA", "LLM_ALLOW_SP_TEXT"))
    for enabled_name in enabled_names:
        if os.getenv(enabled_name, "").strip() != "1":
            missing.append(f"{enabled_name}=1")
    if _remote_provider() == "pgpt" and not (
        os.getenv("OPENAI_RESPONSES_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
    ):
        missing.append("OPENAI_BASE_URL or OPENAI_RESPONSES_URL")
    return sorted(dict.fromkeys(missing))


def _llm_profile_id(default: str = "openai_sp_semantic_analysis") -> str:
    value = os.getenv("P42_LIVE_LLM_PROFILE_ID", default).strip()
    if value in {"openai_sp_semantic_analysis", "openai_fast_test", "openai_ai_draft_pack"}:
        return value
    return default


def _live_replay_mode() -> str:
    value = os.getenv(LIVE_MODE_ENV, LIVE_MODE_LIVE_PPM).strip().lower()
    if value in {LIVE_MODE_SANITIZED_FIXTURE, "fixture", "safe_fixture"}:
        return LIVE_MODE_SANITIZED_FIXTURE
    return LIVE_MODE_LIVE_PPM


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
