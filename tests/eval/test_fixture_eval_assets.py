from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from api_app.schemas import SPAnalysisRequest
from api_app.workflow import WorkflowService
from ai_agent_domain import CanonicalAnalysisModel

from tests.unit.api.fake_repository import MemoryWorkflowRepository

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "fixtures" / "eval"


def test_eval_fixture_files_parse_and_share_sample_id() -> None:
    request = _json_fixture("request.json")
    canonical = _json_fixture("canonical_analysis_candidate.json")
    artifacts = _json_fixture("artifact_payloads.json")
    rubric = _yaml_fixture("rubric.yaml")

    sample_id = "p06-fixture-workflow-master-order-summary-v1"
    assert request["sampleId"] == sample_id
    assert canonical["sampleId"] == sample_id
    assert artifacts["sampleId"] == sample_id
    assert rubric["fixture"] == sample_id
    assert request["request"]["dbProfileId"] == "master"
    assert request["expected"]["metadataMode"] == "fixture-first"
    assert rubric["thresholds"]["secret_like_value_count"] == 0


def test_eval_fixtures_do_not_contain_secret_like_values() -> None:
    for path in sorted(EVAL_DIR.iterdir()):
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        payload = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.suffix == ".json"
            else yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        offenders = list(_secret_like_values(payload))
        assert offenders == [], (path.name, offenders)


def test_sample_canonical_payload_marks_review_boundaries() -> None:
    canonical = _json_fixture("canonical_analysis_candidate.json")
    analysis = canonical["analysis_local"]

    assert canonical["target_contract"] == "CanonicalAnalysisModel"
    assert canonical["status"] == "CONTRACT_CLOSED"
    assert canonical["analysis_status"] == "REVIEW_REQUIRED"
    assert canonical["blockers"] == []
    assert CanonicalAnalysisModel.model_validate(analysis).snapshot_id == (
        "mcp-fixture-snapshot-0001"
    )
    assert analysis["procedure"]["identifier"]["full_name"] == "dbo.usp_GetOrderSummary"
    assert analysis["dependencies"]["table_references"][1]["status"] == "REVIEW_REQUIRED"
    assert analysis["review_markers"][0]["code"] == "AMBIGUOUS_ORDER_LINE_DEPENDENCY"
    assert analysis["canonical_conversion_blockers"] == []


def test_generated_workflow_summary_matches_eval_fixture(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    monkeypatch.setenv("LLM_LIVE_GATE", "0")
    monkeypatch.setenv("LLM_ALLOW_SP_TEXT", "0")
    request_fixture = _json_fixture("request.json")
    expected = _json_fixture("artifact_payloads.json")
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(
        SPAnalysisRequest.model_validate(request_fixture["request"])
    )

    assert request_record.db_profile_id == "master"
    assert job.status.value == expected["workflow"]["jobStatus"]
    assert job.current_step.value == expected["workflow"]["currentStep"]

    artifacts = list(repository.artifacts.values())
    assert [artifact.type.value for artifact in artifacts] == expected["workflow"][
        "artifactTypes"
    ]
    assert "PUBLISHED" not in {artifact.status.value for artifact in artifacts}

    by_type = {artifact.type.value: artifact for artifact in artifacts}
    for artifact_expectation in expected["artifactExpectations"]:
        artifact = by_type[artifact_expectation["type"]]
        assert artifact.status.value == artifact_expectation["status"]
        assert artifact.latest_validation_status == artifact_expectation[
            "latestValidationStatus"
        ]
        assert len(artifact.evidence_refs) >= artifact_expectation["minimumEvidenceRefs"]
        assert artifact.generator_version
        assert artifact.registry_refs
        assert artifact.review_required is True

        for required_content in artifact_expectation.get("requiredContent", []):
            assert required_content in artifact.content

        marker = artifact_expectation.get("requiredAssumptionMarker")
        if marker:
            assert any(marker in assumption for assumption in artifact.assumptions)

    assert any(event.action == "METADATA_COLLECTED" for event in repository.audit_events)
    assert "PUBLISH_GATE_EVALUATED" not in {event.action for event in repository.audit_events}


def _json_fixture(name: str) -> dict[str, Any]:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def _yaml_fixture(name: str) -> dict[str, Any]:
    return yaml.safe_load((EVAL_DIR / name).read_text(encoding="utf-8"))


def _secret_like_values(payload: Any, path: str = "$") -> Iterator[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).lower()
            nested_path = f"{path}.{key}"
            if any(marker in key_text for marker in ("password", "secret", "token", "api_key")):
                if value not in ("", None, 0):
                    yield nested_path
            yield from _secret_like_values(value, nested_path)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            yield from _secret_like_values(item, f"{path}[{index}]")
