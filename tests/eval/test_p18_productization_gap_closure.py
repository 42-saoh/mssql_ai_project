from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import CanonicalAnalysisModel

ROOT = Path(__file__).resolve().parents[2]
P18_FIXTURE = ROOT / "fixtures" / "eval" / "productization_gap_closure_p18_v1.yaml"
P17_FIXTURE = ROOT / "fixtures" / "eval" / "live_pilot_blocker_closure_p17_v1.yaml"
CANONICAL_CANDIDATE = ROOT / "fixtures" / "eval" / "canonical_analysis_candidate.json"
WEB_ROOT = ROOT / "apps" / "web"
WEB_HTTP_SMOKE = WEB_ROOT / "scripts" / "http-adapter-smoke.mjs"
WEB_PACKAGE = WEB_ROOT / "package.json"
WEB_HTTP_RUNNER = ROOT / "tests" / "e2e" / "web_http_adapter_smoke.py"
AUTH_SOURCE_DOC = ROOT / "docs" / "admin-guide" / "auth-rbac-production-source.md"
AUTH_SOURCE_ADR = ROOT / "docs" / "adr" / "ADR-0006-production-auth-rbac-source.md"


def test_p18_fixture_preserves_p17_conditional_go_but_keeps_productization_no_go() -> None:
    fixture = _yaml(P18_FIXTURE)
    p17 = _yaml(P17_FIXTURE)

    assert fixture["version"] == "productization_gap_closure_p18_v1"
    assert fixture["current_state"]["p17_scoped_live_pilot_decision"] == (
        p17["final_decision_policy"]["current_decision"]
    )
    assert fixture["current_state"]["p17_scoped_live_pilot_decision"] == "CONDITIONAL_GO"
    assert fixture["current_state"]["p18_productization_decision"] == "NO_GO"
    assert fixture["current_state"]["production_ready"] is False
    assert fixture["p18_final_gate"]["p17_conditional_go_preserved"] is True
    assert fixture["p18_final_gate"]["current_productization_decision"] == "NO_GO"

    blockers = {blocker["code"] for blocker in fixture["active_productization_blockers"]}
    assert blockers == {"AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED"}


def test_p18a_canonical_contract_gap_is_exact_and_evidence_safe() -> None:
    fixture = _yaml(P18_FIXTURE)
    canonical = _json_like_yaml(CANONICAL_CANDIDATE)
    p18a = fixture["p18a_canonical_analysis_model"]

    assert p18a["current_candidate_contract"] == canonical["analysis_local"][
        "contract_target"
    ]
    assert p18a["target_contract"] == canonical["target_contract"]
    assert p18a["current_status"] == canonical["status"] == "CONTRACT_CLOSED"
    assert p18a["analysis_status"] == canonical["analysis_status"] == "REVIEW_REQUIRED"
    assert p18a["current_blockers"] == []
    assert canonical["blockers"] == []
    assert p18a["exact_contract_blockers"] == []
    assert {
        "DOMAIN_CANONICAL_SCHEMA_MISSING",
        "SNAPSHOT_ID_BINDING_MISSING",
        "REGISTRY_VERSION_REFS_MISSING",
        "MODERNIZATION_POINTS_SCHEMA_MISSING",
    } == set(p18a["closed_contract_blockers"])
    model = CanonicalAnalysisModel.model_validate(canonical["analysis_local"])
    assert model.snapshot_id == "mcp-fixture-snapshot-0001"
    assert model.registry_version_refs
    assert model.evidence_refs
    assert "modernization_points" in canonical["analysis_local"]
    assert p18a["uncertainty_policy"]["dynamic_sql_unresolved"] == "REVIEW_REQUIRED"
    assert p18a["release_critical_review_required_allowed"] is False

    serialized = P18_FIXTURE.read_text(encoding="utf-8").lower()
    assert "select *" not in serialized
    assert "count(*)" not in serialized
    assert "password:" not in serialized


def test_p18b_web_http_and_auth_boundaries_are_explicit() -> None:
    fixture = _yaml(P18_FIXTURE)
    p18b = fixture["p18b_web_http_auth_rbac"]
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(encoding="utf-8")
    client = (WEB_ROOT / "lib" / "api" / "client.ts").read_text(encoding="utf-8")

    assert p18b["http_adapter"]["current_status"] == "RELEASE_SMOKE_RECORDED"
    assert p18b["http_adapter"]["default_mode"] == "mock"
    assert p18b["http_adapter"]["http_mode_env"] == "PORTAL_API_MODE=http"
    assert p18b["http_adapter"]["smoke_script_path"] == (
        "apps/web/scripts/http-adapter-smoke.mjs"
    )
    assert p18b["http_adapter"]["local_smoke_runner_path"] == (
        "tests/e2e/web_http_adapter_smoke.py"
    )
    assert p18b["http_adapter"]["local_smoke_command"] == (
        "python3 tests/e2e/web_http_adapter_smoke.py"
    )
    assert "PORTAL_API_MODE" in client
    assert "PORTAL_API_BASE_URL" in client

    required_fragments = (
        "/api/v1/requests/sp-analysis",
        "/api/v1/jobs/",
        "/artifacts",
        "/api/v1/artifacts/",
        "/validation",
        "/approval-decisions",
        "/api/v1/metadata/db-profiles",
        "/api/v1/metadata/search",
        "/api/v1/registry/versions",
    )
    for fragment in required_fragments:
        assert fragment in http_client

    smoke_script = WEB_HTTP_SMOKE.read_text(encoding="utf-8")
    package_json = WEB_PACKAGE.read_text(encoding="utf-8")
    runner = WEB_HTTP_RUNNER.read_text(encoding="utf-8")
    assert "createHttpPortalApi" in smoke_script
    assert "observedRequests" in smoke_script
    assert "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED" in smoke_script
    assert "smoke:http-adapter" in package_json
    assert "uvicorn.Server" in runner
    assert "MemoryWorkflowRepository" in runner

    auth = p18b["auth_rbac"]
    assert auth["current_status"] == (
        "SOURCE_DOCUMENTED_ENFORCEMENT_IMPLEMENTED_LIVE_WIRING_PENDING"
    )
    assert auth["blocker"] == "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED"
    assert auth["enforcement"]["enabled_by_env"] == "AUTH_RBAC_ENFORCEMENT"
    assert auth["enforcement"]["unauthorized_negative_tests"] == (
        "tests/integration/api/test_api_auth_rbac.py"
    )
    assert auth["enforcement"]["live_wiring_status"] == "UNVERIFIED"
    assert auth["must_not_fake_with_mock_headers"] is True
    assert auth["documented_source"]["identity_source"].startswith("verified OIDC/JWT")
    assert auth["documented_source"]["role_source"] == (
        "PLF AUTH_USERS, AUTH_ROLES, AUTH_USER_ROLES"
    )
    assert auth["documented_source"]["source_doc"] == (
        "docs/admin-guide/auth-rbac-production-source.md"
    )
    assert auth["documented_source"]["adr"] == (
        "docs/adr/ADR-0006-production-auth-rbac-source.md"
    )
    assert auth["documented_source"]["canonical_roles"] == [
        "USER",
        "REVIEWER",
        "ADMIN",
        "AUDITOR",
    ]


def test_p18b_auth_source_docs_define_identity_roles_and_denials() -> None:
    auth_doc = AUTH_SOURCE_DOC.read_text(encoding="utf-8")
    adr = AUTH_SOURCE_ADR.read_text(encoding="utf-8")
    combined = f"{auth_doc}\n{adr}"

    for phrase in (
        "verified OIDC/JWT",
        "AUTH_USERS",
        "AUTH_ROLES",
        "AUTH_USER_ROLES",
        "Role-To-Action Matrix",
        "401 Unauthorized",
        "403 Forbidden",
        "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED",
    ):
        assert phrase in combined

    for role in ("USER", "REVIEWER", "ADMIN", "AUDITOR"):
        assert role in auth_doc

    forbidden_fragments = (
        "Mock headers",
        "hardcoded actors",
        "local password storage",
        "committed tokens",
        "fixture secrets",
    )
    for fragment in forbidden_fragments:
        assert fragment in auth_doc

    assert "JWT group claim only" in adr
    assert "거부" in adr


def test_p18_forbidden_boundaries_remain_closed() -> None:
    fixture = _yaml(P18_FIXTURE)

    assert fixture["policy_boundaries"]["metadata_only"] is True
    assert fixture["policy_boundaries"]["row_data_allowed"] is False
    assert fixture["policy_boundaries"]["procedure_execution_allowed"] is False
    assert fixture["policy_boundaries"]["ddl_dml_allowed"] is False
    assert fixture["policy_boundaries"]["plf_fallback_allowed"] is False
    assert fixture["policy_boundaries"]["production_ready_claim_allowed"] is False
    assert {
        "row_data",
        "procedure_execution",
        "sql_definition_text",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
        "unapproved_publish_or_export",
        "fake_auth_rbac_with_mock_headers",
    } <= set(fixture["forbidden_evidence"])


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _json_like_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
