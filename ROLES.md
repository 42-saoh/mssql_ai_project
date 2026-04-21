# ROLES.md

이 문서는 저장소에서 사용할 역할 카탈로그다.  
Codex CLI에서 서브에이전트를 명시적으로 사용할 때 이 역할을 기준으로 나눈다.

## 역할 설계 원칙

- 각 역할은 좁고 분명한 책임을 가진다.
- 구현 역할과 검토 역할을 분리한다.
- 읽기 전용 탐색 역할과 쓰기 가능한 구현 역할을 구분한다.
- 설계 결정은 문서와 계약으로 남긴다.

## 역할 목록

| 역할 | 주요 책임 | 주 산출물 | 기본 모드 |
|---|---|---|---|
| `architect` | 시스템 구조, 서비스 경계, ADR, API/DDL 계약 | 설계 문서, ADR, 인터페이스 초안 | 읽기 중심 |
| `platform_worker` | API/BFF, workflow, artifact/approval, registry 구현 | 애플리케이션 코드, 테스트, migration | 구현 중심 |
| `mcp_engineer` | MSSQL Metadata MCP 서버, 읽기 전용 메타데이터 어댑터 | MCP tools, schemas, adapters, contract tests | 구현 중심 |
| `template_engineer` | Canonical 모델, 프롬프트/템플릿, 생성기 | models, renderers, templates, generator tests | 설계+구현 |
| `reviewer` | correctness, security, missing tests, docs drift | 리뷰 노트, 수정 요청, 품질 게이트 결과 | 읽기 전용 |
| `docs_curator` | 설계/운영/사용자 문서 정합성 유지 | 문서 업데이트, 예시, 체크리스트 | 문서 편집 |

## 역할 상세

### architect

- 시스템 전반의 구조 일관성을 책임진다.
- 구현보다 경계, 책임, 의존성 방향, 버전 정책을 먼저 정리한다.
- 코드 변경이 필요 없으면 문서와 계약만 제시해도 된다.
- Architecture/API/DDL/Policy 변경 시 반드시 관여한다.

### platform_worker

- `apps/api`, `apps/web`, `packages/*`의 실제 기능 구현을 담당한다.
- 가장 작은 유효 기능 단위로 구현하고 테스트를 붙인다.
- 정책상 금지된 외부 상태 변경은 하지 않는다.
- 문서가 코드와 어긋나면 docs_curator와 함께 동기화한다.

### mcp_engineer

- `services/mssql-mcp`를 담당한다.
- 도구는 정형 파라미터 입력만 받고 자유 SQL 실행기를 만들지 않는다.
- 읽기 전용 메타데이터 범위를 강제한다.
- 실패 케이스, timeout, error code, snapshot/evidence를 계약으로 명확히 한다.

### template_engineer

- `CanonicalAnalysisModel`을 중심으로 문서/코드 생성기의 입력·출력을 정리한다.
- 프롬프트보다 템플릿과 결정론적 렌더링을 우선한다.
- 추론이 필요한 영역은 명시적으로 `REVIEW_REQUIRED` 표시를 남긴다.
- 템플릿 버전과 출력 포맷 호환성을 관리한다.

### reviewer

- 구현 결과를 소유자 관점에서 검토한다.
- correctness, policy compliance, security, missing tests, docs drift를 우선 본다.
- 스타일 지적은 실제 오류 위험을 유발하는 경우만 한다.
- 수정 제안은 재현 단계와 함께 남긴다.

### docs_curator

- `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`, `TASK_TEMPLATE.md`를 최신 상태로 유지한다.
- 구조/정책/명령이 바뀌면 예시까지 함께 갱신한다.
- 중복 문서를 줄이고 참조 구조를 정리한다.

## 권장 협업 패턴

### 패턴 1. 설계 → 구현 → 리뷰
1. `architect` 가 경계/계약을 정리한다.
2. `platform_worker` 또는 `mcp_engineer` 가 구현한다.
3. `reviewer` 가 correctness/security/docs drift를 본다.
4. `docs_curator` 가 문서를 마감한다.

### 패턴 2. 기능 슬라이스 병렬화
- API 계약
- MCP 도구 계약
- validation/eval
- docs sync

위 4개를 병렬로 탐색하고, 최종 통합은 메인 세션이 한다.

## 역할 선택 빠른 기준

- 구조가 불명확하다 → `architect`
- 메타데이터 서버를 건드린다 → `mcp_engineer`
- 앱 코드/테스트를 만든다 → `platform_worker`
- 생성기/템플릿/분석 모델을 다룬다 → `template_engineer`
- 머지 전 검토가 필요하다 → `reviewer`
- 문서가 밀렸다 → `docs_curator`
