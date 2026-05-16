from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from api_app import auth as auth_module
from api_app.dependencies import (
    get_repository,
    get_workflow_service,
    reset_application_state,
)
from api_app.main import app
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository

ISSUER = "https://idp.example.test/"
AUDIENCE = "ai-agent-platform-api"


@dataclass(frozen=True)
class AuthHarness:
    client: TestClient
    repository: MemoryWorkflowRepository
    token_for: Callable[[str], str]


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[AuthHarness]:
    jwt, private_key, public_jwk = _ephemeral_rsa_jwt_material()

    class StaticJwksClient:
        def get_signing_key_from_jwt(self, _token: str):
            return jwt.PyJWK.from_dict(public_jwk)

    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    monkeypatch.setenv("AUTH_RBAC_ENFORCEMENT", "1")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://idp.example.test/.well-known/jwks.json")
    monkeypatch.setattr(auth_module, "build_jwks_client", lambda _url: StaticJwksClient())
    reset_application_state()

    repository = MemoryWorkflowRepository()
    repository.add_auth_actor(
        subject="subject-user",
        login="user@example.com",
        email="user@example.com",
        roles=("USER",),
    )
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service

    def token_for(subject: str) -> str:
        return _token_for(jwt, private_key, subject)

    try:
        yield AuthHarness(TestClient(app), repository, token_for)
    finally:
        app.dependency_overrides.clear()
        reset_application_state()


def test_validation_requires_verified_identity_and_approval_route_is_absent(
    auth_client: AuthHarness,
) -> None:
    artifact_id = _create_artifact(auth_client.client)

    validation = auth_client.client.post(f"/api/v1/artifacts/{artifact_id}/validation")
    approval = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        json={"decision": "REQUEST_CHANGES"},
    )

    assert validation.status_code == 401
    assert validation.json()["code"] == "UNAUTHORIZED"
    assert approval.status_code == 404


def test_user_role_can_validate_without_reviewer_permission(
    auth_client: AuthHarness,
) -> None:
    artifact_id = _create_artifact(auth_client.client)
    headers = _auth_header(auth_client.token_for("subject-user"))

    validation = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/validation",
        headers=headers,
    )
    approval = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={"decision": "REQUEST_CHANGES"},
    )

    assert validation.status_code == 200
    assert validation.json()["artifactId"] == artifact_id
    assert approval.status_code == 404
    validation_audit = [
        event
        for event in auth_client.repository.audit_events
        if event.action == "ARTIFACT_VALIDATED"
    ][-1]
    assert validation_audit.actor == "user@example.com"


def test_knowledge_review_routes_are_absent(
    auth_client: AuthHarness,
) -> None:
    asset = _create_knowledge_asset_version(auth_client.client)
    user_headers = _auth_header(auth_client.token_for("subject-user"))

    posted = auth_client.client.post(
        (
            "/api/v1/knowledge/assets/"
            f"{asset['assetId']}/versions/{asset['currentVersionId']}/review"
        ),
        headers=user_headers,
        json={"status": "REVIEW_REQUIRED"},
    )
    listed = auth_client.client.get(
        f"/api/v1/knowledge/assets/{asset['assetId']}/reviews",
        headers=user_headers,
    )

    assert posted.status_code == 404
    assert listed.status_code == 404


def _create_artifact(client: TestClient) -> str:
    submit = client.post(
        "/api/v1/requests/sp-analysis",
        json={
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": False,
                "useAiToolOrchestration": False,
            },
        },
    )
    assert submit.status_code == 202
    if submit.json()["status"] == "FAILED":
        job = client.get(f"/api/v1/jobs/{submit.json()['jobId']}")
        assert submit.json()["status"] != "FAILED", job.json()
    listed = client.get(f"/api/v1/jobs/{submit.json()['jobId']}/artifacts")
    assert listed.status_code == 200
    return listed.json()["artifacts"][0]["artifactId"]


def _create_knowledge_asset_version(client: TestClient) -> dict:
    submit = client.post(
        "/api/v1/requests/sp-analysis",
        json={
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": False,
                "useAiToolOrchestration": False,
            },
        },
    )
    assert submit.status_code == 202
    if submit.json()["status"] == "FAILED":
        job = client.get(f"/api/v1/jobs/{submit.json()['jobId']}")
        assert submit.json()["status"] != "FAILED", job.json()
    listed = client.get(f"/api/v1/jobs/{submit.json()['jobId']}/knowledge-assets")
    assert listed.status_code == 200
    return next(
        asset
        for asset in listed.json()["knowledgeAssets"]
        if asset["assetKind"] == "SP_ANALYSIS"
    )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(jwt, private_key, subject: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "email": f"{subject.removeprefix('subject-')}@example.com",
        "preferred_username": f"{subject.removeprefix('subject-')}@example.com",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "p19-key"})


def _ephemeral_rsa_jwt_material():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "p19-key"
    public_jwk["alg"] = "RS256"
    return jwt, private_key, public_jwk
