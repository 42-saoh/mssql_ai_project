# Production Auth/RBAC Source

## Status

Production actor and role source is documented for P18B. The active API surface now enforces identity for draft validation and removes decision-gate actions from the product flow. Live IdP/JWKS and PLF role lookup wiring is deferred future hardening, tracked as `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED`. The current platform may be opened for controlled conditional use, but it must not be described as production-grade enterprise Auth/RBAC or `production_ready: true`.

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

The canonical seeded role names are `USER`, `ADMIN`, and `AUDITOR`. JWT group claims may be used only as an upstream hint; effective authorization must be resolved through PLF role membership.

## Role-To-Action Matrix

| Action | USER | ADMIN | AUDITOR |
|---|---:|---:|---:|
| Create analysis request | Allow | Allow | Deny |
| View own job and artifact preview | Allow | Allow | Allow |
| View any job and artifact preview | Deny | Allow | Allow |
| Run artifact validation | Allow | Allow | Deny |
| Manage DB profiles, registry, and policy settings | Deny | Allow | Deny |
| View audit and read-only evidence reports | Deny | Allow | Allow |

Publish/export, deployment, DDL/DML, row-data access, procedure execution, PLF fallback for PPM, and raw SQL definition text remain forbidden regardless of role.

## Error Semantics

- `401 Unauthorized`: no verified OIDC/JWT identity is present, token validation failed, or the actor cannot be mapped to an active `AUTH_USERS` row.
- `403 Forbidden`: identity is verified but the actor does not have a role that allows the requested action.

## Enforcement Status

The active route-level checks cover:

- `POST /api/v1/artifacts/{artifactId}/validation`

Authenticated `USER` and `ADMIN` actors may run validation because validation is a draft quality gate, not a decision action. There is no approval-decision route in the public API.

Negative route coverage lives in `tests/integration/api/test_api_auth_rbac.py`. The tests generate ephemeral JWT signing material at runtime and do not commit tokens or fixture secrets.

Live production wiring remains deferred until an approved IdP/JWKS endpoint and PLF role membership are verified outside the fixture-backed test path. This is not an active blocker for controlled conditional open; it is required before claiming production-grade enterprise Auth/RBAC.

## P20 Live Wiring Gate

The hard-live gate is opt-in future hardening. `AUTH_RBAC_LIVE_GATE=1` and `AUTH_RBAC_ENFORCEMENT=1`
must both be set before the repository contacts the approved IdP/JWKS endpoint or PLF.
Default tests remain fixture-first and do not access production identity infrastructure.

Required local or secret-manager inputs:

- `OIDC_ISSUER`
- `OIDC_AUDIENCE`
- `OIDC_JWKS_URL`
- `OIDC_USER_BEARER_TOKEN`
- `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`,
  `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`

Run:

```bash
AUTH_RBAC_LIVE_GATE=1 AUTH_RBAC_ENFORCEMENT=1 make test PYTEST_ARGS="tests/eval/test_p20_auth_rbac_live_gate.py"
```

The helper `apps/api/scripts/auth_rbac_live_probe.py` performs only JWT verification and
PLF role lookup. It does not call validation routes and does not create workflow,
validation, or audit writes. A passing result may record only redacted evidence:
pass/fail, role category, blocker code, and a short summary.
Missing live env or failed live verification is reported as a deferred prerequisite
failure, not as closure of a productization blocker.

### Assisted login

Playwright MCP may be used only as an Assisted login preflight for an approved
non-production/test IdP or dev portal. The operator handles credentials and MFA, then
places the resulting bearer tokens in local `.env` or an approved secret manager.

Do not use Playwright MCP for arbitrary browser JavaScript token extraction, localStorage
scraping, cookie scraping, storage-state files, token-bearing screenshots, traces,
recordings, or chat-pasted secrets.

Until the live gate passes, `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` remains a
deferred future hardening item. Controlled conditional open remains allowed, but
production-grade enterprise Auth/RBAC and `production_ready: true` claims remain forbidden.
