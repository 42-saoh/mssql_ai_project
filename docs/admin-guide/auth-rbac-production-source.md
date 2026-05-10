# Production Auth/RBAC Source

## Status

Production actor and role source is documented for P18B. P19 adds fixture-covered API enforcement for validation and approval actions. Productization remains `NO_GO` until live IdP/JWKS and PLF role lookup wiring is verified, tracked as `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED`.

## Identity Source

Production actor identity must come from a verified OIDC/JWT boundary. When `AUTH_RBAC_ENFORCEMENT=1`, the API validates bearer JWT signature, issuer, audience, and expiry using `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`. Revocation/session policy remains an upstream IdP or API gateway responsibility.

Required actor mapping:

| JWT claim | Platform use |
|---|---|
| `sub` | Stable actor identifier for audit and ownership checks. |
| `email` or `preferred_username` | Login mapping candidate for `AUTH_USERS.LGN_ID`. |
| `name` | Display-only user name candidate for `AUTH_USERS.USR_NM`. |

Mock headers, hardcoded actors, local password storage, committed tokens, and fixture secrets are not production identity sources.

## Role Source

Production roles are read from the PLF platform DB auth tables:

- `AUTH_USERS`
- `AUTH_ROLES`
- `AUTH_USER_ROLES`

The canonical seeded role names are `USER`, `REVIEWER`, `ADMIN`, and `AUDITOR`. JWT group claims may be used only as an upstream hint; effective authorization must be resolved through PLF role membership.

## Role-To-Action Matrix

| Action | USER | REVIEWER | ADMIN | AUDITOR |
|---|---:|---:|---:|---:|
| Create analysis request | Allow | Allow | Allow | Deny |
| View own job and artifact preview | Allow | Allow | Allow | Allow |
| View any job and artifact preview | Deny | Allow | Allow | Allow |
| Run artifact validation | Deny | Allow | Allow | Deny |
| Record approval decision | Deny | Allow | Allow | Deny |
| Manage DB profiles, registry, and policy settings | Deny | Deny | Allow | Deny |
| View audit and read-only evidence reports | Deny | Deny | Allow | Allow |

Publish/export, deployment, DDL/DML, row-data access, procedure execution, PLF fallback for PPM, and raw SQL definition text remain forbidden regardless of role.

## Error Semantics

- `401 Unauthorized`: no verified OIDC/JWT identity is present, token validation failed, or the actor cannot be mapped to an active `AUTH_USERS` row.
- `403 Forbidden`: identity is verified but the actor does not have a role that allows the requested action.

## Enforcement Status

P19 implements route-level checks for:

- `POST /api/v1/artifacts/{artifactId}/validation`
- `POST /api/v1/artifacts/{artifactId}/approval-decisions`

Both actions require `REVIEWER` or `ADMIN`. Approval decisions also require the request body reviewer to match the verified actor identity, preventing reviewer spoofing.

Negative route coverage lives in `tests/integration/api/test_api_auth_rbac.py`. The tests generate ephemeral JWT signing material at runtime and do not commit tokens or fixture secrets.

Live production wiring remains blocked until an approved IdP/JWKS endpoint and PLF role membership are verified outside the fixture-backed test path.
