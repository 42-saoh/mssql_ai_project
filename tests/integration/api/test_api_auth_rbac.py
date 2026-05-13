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
    repository.add_auth_actor(
        subject="subject-reviewer",
        login="reviewer@example.com",
        email="reviewer@example.com",
        roles=("REVIEWER",),
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


def test_validation_and_approval_require_verified_identity(
    auth_client: AuthHarness,
) -> None:
    artifact_id = _create_artifact(auth_client.client)

    validation = auth_client.client.post(f"/api/v1/artifacts/{artifact_id}/validation")
    approval = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        json={
            "decision": "REQUEST_CHANGES",
            "reviewer": "reviewer@example.com",
            "comment": "missing verified identity",
        },
    )

    assert validation.status_code == 401
    assert validation.json()["code"] == "UNAUTHORIZED"
    assert approval.status_code == 401
    assert approval.json()["code"] == "UNAUTHORIZED"


def test_validation_and_approval_reject_user_role(
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
        json={
            "decision": "REQUEST_CHANGES",
            "reviewer": "user@example.com",
            "comment": "USER role cannot record decisions",
        },
    )

    assert validation.status_code == 403
    assert validation.json()["code"] == "FORBIDDEN"
    assert approval.status_code == 403
    assert approval.json()["code"] == "FORBIDDEN"


def test_reviewer_role_can_validate_and_record_matching_approval(
    auth_client: AuthHarness,
) -> None:
    artifact_id = _create_artifact(auth_client.client)
    headers = _auth_header(auth_client.token_for("subject-reviewer"))

    validation = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/validation",
        headers=headers,
    )
    approval = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={
            "decision": "REQUEST_CHANGES",
            "reviewer": "reviewer@example.com",
            "comment": "verified reviewer decision",
        },
    )

    assert validation.status_code == 200
    assert validation.json()["artifactId"] == artifact_id
    assert approval.status_code == 201
    assert approval.json()["reviewer"] == "reviewer@example.com"
    validation_audit = [
        event
        for event in auth_client.repository.audit_events
        if event.action == "ARTIFACT_VALIDATED"
    ][-1]
    approval_audit = [
        event
        for event in auth_client.repository.audit_events
        if event.action == "APPROVAL_DECISION_RECORDED"
    ][-1]
    assert validation_audit.actor == "reviewer@example.com"
    assert approval_audit.actor == "reviewer@example.com"


def test_approval_rejects_reviewer_spoofing(
    auth_client: AuthHarness,
) -> None:
    artifact_id = _create_artifact(auth_client.client)
    headers = _auth_header(auth_client.token_for("subject-reviewer"))

    approval = auth_client.client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={
            "decision": "REQUEST_CHANGES",
            "reviewer": "other-reviewer@example.com",
            "comment": "body reviewer must not spoof identity",
        },
    )

    assert approval.status_code == 403
    assert approval.json()["code"] == "FORBIDDEN"
    assert "verified actor" in approval.json()["detail"]


def test_knowledge_review_requires_reviewer_role_and_prevents_spoofing(
    auth_client: AuthHarness,
) -> None:
    asset = _create_knowledge_asset_version(auth_client.client)
    user_headers = _auth_header(auth_client.token_for("subject-user"))
    reviewer_headers = _auth_header(auth_client.token_for("subject-reviewer"))

    denied = auth_client.client.post(
        (
            "/api/v1/knowledge/assets/"
            f"{asset['assetId']}/versions/{asset['currentVersionId']}/review"
        ),
        headers=user_headers,
        json={
            "status": "REVIEWED",
            "reasonCode": "USER_CANNOT_REVIEW",
            "reviewer": "user@example.com",
        },
    )
    reviewed = auth_client.client.post(
        (
            "/api/v1/knowledge/assets/"
            f"{asset['assetId']}/versions/{asset['currentVersionId']}/review"
        ),
        headers=reviewer_headers,
        json={
            "status": "REVIEWED",
            "reasonCode": "VERIFIED_REVIEWER",
            "reviewer": "reviewer@example.com",
            "comment": "reviewed sanitized knowledge",
        },
    )
    spoofed = auth_client.client.post(
        (
            "/api/v1/knowledge/assets/"
            f"{asset['assetId']}/versions/{asset['currentVersionId']}/review"
        ),
        headers=reviewer_headers,
        json={
            "status": "ARCHIVED",
            "reasonCode": "SPOOF_REJECTED",
            "reviewer": "other-reviewer@example.com",
        },
    )

    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewer"] == "reviewer@example.com"
    assert spoofed.status_code == 403
    assert spoofed.json()["code"] == "FORBIDDEN"
    review_audit = [
        event
        for event in auth_client.repository.audit_events
        if event.action == "KNOWLEDGE_ASSET_REVIEW_RECORDED"
    ][-1]
    assert review_audit.actor == "reviewer@example.com"


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
