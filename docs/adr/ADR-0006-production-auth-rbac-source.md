# ADR-0006 — Production auth/RBAC source is verified OIDC/JWT plus PLF role lookup

## 상태
Accepted

## 결정
- Production actor identity source 는 외부 IdP 또는 API gateway 가 검증한 OIDC/JWT 로 둔다.
- API 는 검증된 JWT 의 `sub` 를 stable actor id 로 사용하고, `email` 또는 `preferred_username` 을 `AUTH_USERS.LGN_ID` 매핑 후보로 사용한다.
- Production role source 는 PLF platform DB 의 `AUTH_USERS`, `AUTH_ROLES`, `AUTH_USER_ROLES` 이다.
- Canonical role name 은 DDL seed 와 동일한 `USER`, `REVIEWER`, `ADMIN`, `AUDITOR` 로 유지한다.
- P19 는 `AUTH_RBAC_ENFORCEMENT=1` 일 때 validation/approval route 에 OIDC/JWT 검증과 PLF role lookup 기반 enforcement 를 적용한다.
- Live IdP/JWKS 와 PLF role membership 이 승인된 환경에서 검증되기 전까지 productization 은 `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` blocker 로 `NO_GO` 를 유지한다.

## 이유
- OIDC/JWT 는 production identity 검증을 app-local password 나 mock header 에 두지 않게 한다.
- PLF role lookup 은 이미 존재하는 platform DB auth table 과 audit FK 설계를 source of truth 로 사용한다.
- JWT group claim 만으로 authorization 을 확정하면 PLF role/audit source 와 drift 가 생길 수 있다.

## 대안
- Mock header 또는 hardcoded actor: production identity source 로 가장하므로 거부한다.
- PLF local password/session: 현재 schema 와 secret policy 가 production credential lifecycle 을 정의하지 않으므로 거부한다.
- JWT group claim only: role membership audit 와 운영 변경 이력을 PLF 에 남기기 어렵기 때문에 거부한다.

## 영향
- API/BFF auth middleware/dependency 는 token validation, active user lookup, role lookup, route action mapping 을 분리한다.
- `401 Unauthorized` 는 verified identity 가 없거나 active user mapping 이 실패할 때 반환한다.
- `403 Forbidden` 은 verified identity 가 있지만 role-to-action matrix 를 만족하지 못할 때 반환한다.
- Validation/approval action 은 unauthorized negative test 와 reviewer spoofing negative test 로 보호한다.
