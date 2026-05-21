from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, status

from api_app.errors import api_http_exception

CANONICAL_ROLES = frozenset({"USER", "ADMIN", "AUDITOR"})
JWT_ALGORITHMS = ("RS256", "PS256", "ES256")


class AuthConfigurationError(RuntimeError):
    """Raised when production auth/RBAC is enabled without required OIDC settings."""


class AuthenticationRequiredError(RuntimeError):
    """Raised when a request has no verified production identity."""


@dataclass(frozen=True)
class AuthSettings:
    enforcement_enabled: bool
    issuer: str
    audience: str
    jwks_url: str

    @property
    def oidc_configured(self) -> bool:
        return bool(self.issuer and self.audience and self.jwks_url)


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str | None = None
    preferred_username: str | None = None
    name: str | None = None

    @property
    def lookup_candidates(self) -> tuple[str, ...]:
        candidates = (
            self.preferred_username,
            self.email,
            self.subject,
        )
        normalized: list[str] = []
        for candidate in candidates:
            value = (candidate or "").strip()
            if value and value not in normalized:
                normalized.append(value)
        return tuple(normalized)


@dataclass(frozen=True)
class Actor:
    actor_id: str
    login: str
    email: str | None
    roles: frozenset[str]
    display_name: str | None = None


class AuthRoleRepository(Protocol):
    def resolve_actor_roles(self, identity: VerifiedIdentity) -> Actor | None:
        ...


class OidcJwtVerifier:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    def verify(self, token: str) -> VerifiedIdentity:
        if not self.settings.oidc_configured:
            raise AuthConfigurationError(
                "AUTH_RBAC_ENFORCEMENT requires OIDC_ISSUER, OIDC_AUDIENCE, "
                "and OIDC_JWKS_URL."
            )
        try:
            import jwt
        except Exception:  # pragma: no cover - dependency/runtime issue
            raise AuthConfigurationError(
                "PyJWT with crypto support is required for OIDC/JWT enforcement."
            ) from None

        try:
            signing_key = build_jwks_client(self.settings.jwks_url).get_signing_key_from_jwt(
                token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(JWT_ALGORITHMS),
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "sub"]},
            )
        except Exception as exc:
            raise AuthenticationRequiredError(
                "Verified OIDC/JWT identity is required."
            ) from exc
        return identity_from_claims(claims)


def build_jwks_client(jwks_url: str):
    import jwt

    return jwt.PyJWKClient(jwks_url)


def load_auth_settings() -> AuthSettings:
    return AuthSettings(
        enforcement_enabled=env_bool("AUTH_RBAC_ENFORCEMENT", default=False),
        issuer=os.getenv("OIDC_ISSUER", "").strip(),
        audience=os.getenv("OIDC_AUDIENCE", "").strip(),
        jwks_url=os.getenv("OIDC_JWKS_URL", "").strip(),
    )


def env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_bearer_token(authorization: str | None) -> str:
    value = (authorization or "").strip()
    if not value:
        raise AuthenticationRequiredError("Authorization bearer token is required.")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationRequiredError("Authorization bearer token is required.")
    return token.strip()


def identity_from_claims(claims: dict[str, Any]) -> VerifiedIdentity:
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationRequiredError("Verified OIDC/JWT identity requires sub.")
    return VerifiedIdentity(
        subject=subject,
        email=string_claim(claims, "email"),
        preferred_username=string_claim(claims, "preferred_username"),
        name=string_claim(claims, "name"),
    )


def string_claim(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def canonical_role_set(
    roles: set[str] | frozenset[str] | tuple[str, ...] | list[str],
) -> frozenset[str]:
    return frozenset(
        role
        for role in (str(item).strip().upper() for item in roles)
        if role in CANONICAL_ROLES
    )


def unauthorized_exception(
    detail: str = "Verified OIDC/JWT identity is required.",
) -> HTTPException:
    return api_http_exception(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        code="UNAUTHORIZED",
    )


def forbidden_exception(detail: str = "Actor role does not allow this action.") -> HTTPException:
    return api_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
        code="FORBIDDEN",
    )
