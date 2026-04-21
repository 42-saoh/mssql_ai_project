# TOOLS.md

## 목적

이 문서는 로컬 개발에서 사용할 도구, 명령 규약, MCP 구성을 정의한다.  
실제 저장소에 아직 명령이 없더라도, 부트스트랩 단계에서는 이 문서를 기준으로 표준 명령을 만든다.

## Codex 운용 기준

### 기본 프로필

- 기본: `safe-explore`
  - 읽기 전용 탐색
  - 설계/리뷰/조사 작업에 사용

### 구현 프로필

- 구현: `dev-edit`
  - workspace 내 편집 허용
  - 작은 기능 슬라이스 구현에 사용

### 리뷰 프로필

- 리뷰: `review`
  - 읽기 전용
  - correctness / security / docs drift 점검에 사용

## 표준 루트 명령

아래 명령은 저장소가 갖춰야 할 표준 루트 인터페이스다.  
없으면 부트스트랩 단계에서 추가한다.

| 명령 | 목적 |
|---|---|
| `make setup` | 로컬 개발 의존성 설치 및 환경 초기화 |
| `make fmt` | 코드 포맷팅 |
| `make lint` | 정적 분석 및 lint |
| `make test` | 도커 테스트 러너에서 파이썬 테스트 실행 |
| `make check` | `fmt + lint + dockerized test` 또는 동등한 게이트 |
| `make run-api` | API/BFF 로컬 실행 |
| `make run-web` | 포털 로컬 실행 |
| `make run-mcp` | MSSQL Metadata MCP 서버 로컬 실행 |
| `make eval` | eval/fixture/rubric 실행 |
| `make test-build` | 도커 테스트 러너 이미지 준비 |
| `make test-web-smoke` | 도커 컨테이너에서 web build smoke 실행 |

## 권장 로컬 도구

### 공통 CLI
- `git`
- `rg`
- `fd`
- `jq`
- `sed`, `awk`
- `make`

### Python 계열
- `python`
- `uv` 또는 `pip`
- `pytest`
- `ruff`
- `mypy`

### Web 계열
- `node`
- `pnpm`
- `eslint`
- `vitest`

### DB / 인프라
- `docker compose`
- `sqlcmd` 또는 동등한 MSSQL CLI

## MCP 서버 기준

### 필수 MCP
- `mssqlMetadata`
  - 목적: MSSQL 메타데이터 조회
  - 범위: procedure/table/column/index/constraint/function/view/extended property
  - 제약: 읽기 전용, 자유 SQL 금지, 실제 데이터 접근 금지

### 선택 MCP
- `openaiDeveloperDocs`
  - 목적: OpenAI/Codex 관련 공식 문서 확인
  - 사용 시점: Codex config, skills, AGENTS, MCP, subagents 관련 규칙 확인
- `context7`
  - 목적: 최신 프레임워크/라이브러리 문서 확인
  - 사용 시점: FastAPI, Next.js, Pydantic, Playwright 등 외부 라이브러리 최신 문맥이 필요한 구현
- `playwright`
  - 목적: 로컬/승인된 dev URL 에 대한 비파괴적 UI smoke 검증
  - 사용 시점: request/job/artifact 화면 확인, build 이후 기본 동작 검증

## 환경 파일 규칙

- `.env.example` 를 항상 유지한다.
- 실제 비밀 값은 `.env.local` 또는 OS keychain 에 둔다.
- 비밀 값은 테스트 fixture, snapshot, log, docs 에 넣지 않는다.
- MCP/DB 연결 문자열은 로컬 개발용 프로필과 분리한다.

## 로그와 추적

- 모든 장시간 작업은 `request_id`, `job_id`, `artifact_id` 를 로그 문맥에 포함한다.
- validation / approval / publish 이벤트는 감사 로그 대상이다.
- 생성 결과에는 `snapshot_id`, `registry_version_refs`, `generator_version` 을 남긴다.

## 명령 사용 규칙

- 먼저 가장 좁은 검증을 돌린다.
- 실패한 명령은 원인 분석 없이 반복 실행하지 않는다.
- 외부 네트워크가 필요한 설치나 문서 조회는 목적을 분명히 하고 최소화한다.
- 저장소 바깥을 쓰는 명령, 파괴적 git 명령, 공유 DB를 건드리는 명령은 기본 금지다.

## 권장 초기 기술 스택

초기 구현 기준으로 아래 조합을 권장한다.  
팀이 다른 스택을 확정하면 이 문서를 먼저 갱신한다.

- `apps/web`: Next.js + TypeScript
- `apps/api`: Python + FastAPI
- `services/mssql-mcp`: Python
- `packages/*`: Python packages 중심
- `Platform DB`: SQL Server
- `Object Storage`: 로컬 파일시스템 시작, 이후 S3 호환 스토리지 확장 가능

## 외부 DB / 스키마 운영

- 플랫폼 DB 와 메타데이터 소스 DB 는 외부 인프라에서 관리한다.
- 저장소는 DB up/down 명령이나 local DB lifecycle 을 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.
- `sqlcmd` 또는 동등한 CLI 는 필요하면 수동 운영 절차에서만 사용한다.

## Docker 기반 테스트 실행

- `docker/test/docker-compose.yml` 이 기본 테스트 러너 정의를 가진다.
- `make test` 는 파이썬 테스트를 컨테이너 안에서 실행한다.
- `make test-web-smoke` 는 현재 web 자동 테스트 공백을 보완하는 컨테이너 기반 build smoke 다.
- 새 테스트 스위트를 추가할 때는 가능하면 도커 실행 경로를 함께 제공한다.
- 외부 DB 연결이 필요한 경우 환경변수로 주입하되, 테스트 명령이 DB lifecycle 을 대신 관리하지는 않는다.
