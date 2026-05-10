#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from api_app.auth import (  # noqa: E402
    ARTIFACT_REVIEW_ROLES,
    AuthConfigurationError,
    AuthenticationRequiredError,
    OidcJwtVerifier,
    load_auth_settings,
)
from api_app.platform_db import (  # noqa: E402
    MssqlPlatformRepository,
    PlatformPersistenceError,
    load_platform_db_settings,
)

DEFERRED_ITEM = "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED"
LIVE_GATE_ENV = "AUTH_RBAC_LIVE_GATE"
REQUIRED_ENV = (
    "AUTH_RBAC_LIVE_GATE",
    "AUTH_RBAC_ENFORCEMENT",
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REVIEWER_BEARER_TOKEN",
    "OIDC_USER_BEARER_TOKEN",
    "PLATFORM_DB_HOST",
    "PLATFORM_DB_PORT",
    "PLATFORM_DB_USER",
    "PLATFORM_DB_PASSWORD",
    "PLATFORM_DB_NAME",
)


def run_probe(*, load_dotenv: bool = True) -> dict[str, Any]:
    if load_dotenv:
        load_root_dotenv()

    if not _flag_enabled(LIVE_GATE_ENV):
        return _result(
            status="skipped",
            blocker_code=None,
            summary=(
                "AUTH_RBAC_LIVE_GATE is not enabled; fixture-first eval did not access "
                "IdP/JWKS or PLF."
            ),
            checks=[],
        )

    missing = _missing_required_env()
    if missing:
        return _result(
            status="failed",
            blocker_code="AUTH_RBAC_LIVE_REQUIRED_ENV_MISSING",
            summary=(
                "Optional live auth/RBAC future-hardening gate is enabled, but "
                "required env names are missing."
            ),
            checks=[
                _check(
                    "required_env",
                    "fail",
                    blocker_code="AUTH_RBAC_LIVE_REQUIRED_ENV_MISSING",
                    summary=(
                        "Deferred prerequisite missing env name(s): "
                        + ", ".join(missing)
                    ),
                )
            ],
        )

    if os.getenv("AUTH_RBAC_ENFORCEMENT", "").strip() != "1":
        return _result(
            status="failed",
            blocker_code="AUTH_RBAC_ENFORCEMENT_DISABLED",
            summary=(
                "AUTH_RBAC_ENFORCEMENT must be 1 for the optional live "
                "future-hardening gate."
            ),
            checks=[
                _check(
                    "auth_enforcement_flag",
                    "fail",
                    blocker_code="AUTH_RBAC_ENFORCEMENT_DISABLED",
                    summary=(
                        "Deferred prerequisite AUTH_RBAC_ENFORCEMENT is present "
                        "but not enabled."
                    ),
                )
            ],
        )

    verifier = OidcJwtVerifier(load_auth_settings())
    repository = MssqlPlatformRepository(load_platform_db_settings())
    checks = [
        _verify_reviewer(verifier, repository),
        _verify_user_without_review_role(verifier, repository),
        _verify_missing_token_semantics(verifier),
        _verify_invalid_token_semantics(verifier),
    ]
    failures = [item for item in checks if item["status"] != "pass"]
    if failures:
        return _result(
            status="failed",
            blocker_code=str(failures[0].get("blockerCode") or DEFERRED_ITEM),
            summary=(
                "Optional live IdP/JWKS and PLF role wiring did not satisfy the "
                "future-hardening gate."
            ),
            checks=checks,
        )
    return _result(
        status="passed",
        blocker_code=None,
        summary=(
            "Live IdP/JWKS verification and PLF role lookup passed with redacted "
            "role-category evidence."
        ),
        checks=checks,
    )


def load_root_dotenv(path: Path | None = None) -> None:
    dotenv = path or REPO_ROOT / ".env"
    if not dotenv.exists():
        return
    for raw_line in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _unquote_env_value(value.strip())


def _verify_reviewer(
    verifier: OidcJwtVerifier,
    repository: MssqlPlatformRepository,
) -> dict[str, Any]:
    actor_result = _verified_actor(
        verifier,
        repository,
        os.environ["OIDC_REVIEWER_BEARER_TOKEN"],
        token_label="reviewer",
    )
    if actor_result["status"] != "pass":
        return actor_result
    roles = actor_result.pop("_roles")
    if not roles.intersection(ARTIFACT_REVIEW_ROLES):
        return _check(
            "reviewer_token_plf_role",
            "fail",
            role_category=_role_category(roles),
            blocker_code="AUTH_RBAC_LIVE_REVIEWER_ROLE_MISMATCH",
            summary="Reviewer token mapped to PLF actor without REVIEWER or ADMIN membership.",
        )
    return _check(
        "reviewer_token_plf_role",
        "pass",
        role_category="REVIEWER_OR_ADMIN",
        summary="Reviewer token verified by JWKS and mapped to PLF review-capable role.",
    )


def _verify_user_without_review_role(
    verifier: OidcJwtVerifier,
    repository: MssqlPlatformRepository,
) -> dict[str, Any]:
    actor_result = _verified_actor(
        verifier,
        repository,
        os.environ["OIDC_USER_BEARER_TOKEN"],
        token_label="user",
    )
    if actor_result["status"] != "pass":
        return actor_result
    roles = actor_result.pop("_roles")
    if roles.intersection(ARTIFACT_REVIEW_ROLES):
        return _check(
            "user_token_role_separation",
            "fail",
            role_category=_role_category(roles),
            blocker_code="AUTH_RBAC_LIVE_USER_ROLE_SEPARATION_FAILED",
            summary="User token mapped to a validation/approval-capable PLF role.",
        )
    return _check(
        "user_token_role_separation",
        "pass",
        role_category="NO_VALIDATION_APPROVAL_ROLE",
        summary="User token verified by JWKS and mapped to PLF actor without review role.",
    )


def _verified_actor(
    verifier: OidcJwtVerifier,
    repository: MssqlPlatformRepository,
    token: str,
    *,
    token_label: str,
) -> dict[str, Any]:
    try:
        identity = verifier.verify(token)
    except AuthConfigurationError:
        return _check(
            f"{token_label}_token_oidc_verification",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_OIDC_CONFIGURATION_INVALID",
            summary="OIDC/JWKS settings are not usable for live token verification.",
        )
    except AuthenticationRequiredError:
        return _check(
            f"{token_label}_token_oidc_verification",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_TOKEN_VERIFICATION_FAILED",
            summary=f"{token_label.title()} token was rejected by OIDC/JWKS verification.",
        )

    try:
        actor = repository.resolve_actor_roles(identity)
    except PlatformPersistenceError:
        return _check(
            f"{token_label}_token_plf_lookup",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_PLF_ROLE_LOOKUP_FAILED",
            summary="PLF AUTH_USERS/AUTH_ROLES/AUTH_USER_ROLES lookup failed.",
        )

    if actor is None:
        return _check(
            f"{token_label}_token_plf_lookup",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_ACTOR_MAPPING_FAILED",
            summary=f"{token_label.title()} token did not map to one active PLF actor.",
        )
    return {
        **_check(
            f"{token_label}_token_plf_lookup",
            "pass",
            summary=f"{token_label.title()} token mapped to one active PLF actor.",
        ),
        "_roles": actor.roles,
    }


def _verify_missing_token_semantics(verifier: OidcJwtVerifier) -> dict[str, Any]:
    try:
        verifier.verify("")
    except AuthenticationRequiredError:
        return _check(
            "missing_token_401_semantics",
            "pass",
            summary="Missing token is rejected with authentication-required semantics.",
        )
    except AuthConfigurationError:
        return _check(
            "missing_token_401_semantics",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_OIDC_CONFIGURATION_INVALID",
            summary="OIDC/JWKS settings are not usable for missing-token semantics.",
        )
    return _check(
        "missing_token_401_semantics",
        "fail",
        blocker_code="AUTH_RBAC_LIVE_401_SEMANTICS_FAILED",
        summary="Missing token was accepted unexpectedly.",
    )


def _verify_invalid_token_semantics(verifier: OidcJwtVerifier) -> dict[str, Any]:
    try:
        verifier.verify("not-a-jwt")
    except AuthenticationRequiredError:
        return _check(
            "invalid_token_401_semantics",
            "pass",
            summary="Invalid token is rejected with authentication-required semantics.",
        )
    except AuthConfigurationError:
        return _check(
            "invalid_token_401_semantics",
            "fail",
            blocker_code="AUTH_RBAC_LIVE_OIDC_CONFIGURATION_INVALID",
            summary="OIDC/JWKS settings are not usable for invalid-token semantics.",
        )
    return _check(
        "invalid_token_401_semantics",
        "fail",
        blocker_code="AUTH_RBAC_LIVE_401_SEMANTICS_FAILED",
        summary="Invalid token was accepted unexpectedly.",
    )


def _missing_required_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.getenv(name, "").strip()]


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _role_category(roles: frozenset[str]) -> str:
    if roles.intersection(ARTIFACT_REVIEW_ROLES):
        return "REVIEWER_OR_ADMIN"
    if roles == frozenset({"USER"}):
        return "USER_ONLY"
    if roles:
        return "NON_REVIEW_ACTOR"
    return "NO_CANONICAL_ROLE"


def _result(
    *,
    status: str,
    blocker_code: str | None,
    summary: str,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "suite": "p20_auth_rbac_live_gate",
        "status": status,
        "deferredItem": DEFERRED_ITEM,
        "productizationBlocking": False,
        "blockerCode": blocker_code,
        "summary": summary,
        "redaction": {
            "tokens": "not_returned",
            "rawJwtClaims": "not_returned",
            "plfRows": "not_returned",
            "connectionStrings": "not_returned",
        },
        "checks": [_public_check(item) for item in checks],
    }


def _check(
    name: str,
    status: str,
    *,
    role_category: str | None = None,
    blocker_code: str | None = None,
    summary: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": status,
        "summary": summary,
    }
    if role_category:
        payload["roleCategory"] = role_category
    if blocker_code:
        payload["blockerCode"] = blocker_code
    return payload


def _public_check(check: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in check.items() if not key.startswith("_")}


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def main() -> int:
    result = run_probe()
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
