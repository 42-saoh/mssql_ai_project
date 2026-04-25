# Codex Parallel Request Pack

이 디렉터리는 **로컬 Codex CLI 병렬 개발**을 위한 운영 패키지다.
현재 기준은 저장소의 OpenAPI skeleton, Platform DB DDL draft, MCP catalog, validation rules, policy files, `.env.sample`, Python/Web lockfile 을 먼저 읽고 각 트랙이 자기 경로만 구현하는 방식이다.

구성:
- `PARALLEL_REQUEST_PLAN.md` — 병렬 개발 웨이브, 트랙, 의존성, 병합 순서
- `PARALLEL_RUNBOOK.md` — worktree 기반 로컬 실행 절차
- `REQUEST_MANIFEST.yaml` — 트랙별 메타데이터, 담당 경로, 프롬프트 매핑
- `prompts/*.md` — Codex 세션에 넣을 수 있는 요청 프롬프트

권장 사용 순서:
1. `PARALLEL_REQUEST_PLAN.md` 읽기
2. `PARALLEL_RUNBOOK.md` 기준으로 worktree 준비
3. `.env.sample` 을 `.env` 로 복사하고 로컬 secret 은 커밋하지 않기
4. `prompts/00_coordinator_baseline.md` 를 메인 코디네이터 세션에 먼저 실행
5. Wave 1 프롬프트를 각 worktree의 Codex 세션에 분산 실행
6. Wave 1 머지 후 `prompts/05_api_workflow.md`
7. 통합 후 `prompts/06_integration_eval_docs.md`
8. 마지막에 `prompts/07_final_review.md`

핵심 규칙:
- 한 트랙은 자기 `Target Files/Dirs` 바깥을 수정하지 않는다.
- 공유 계약 파일은 코디네이터가 먼저 고정한 뒤 worker는 읽기 전용으로 취급한다.
- 병렬 세션끼리 같은 파일을 수정하지 않는다.
- block 되면 범위를 넓히지 말고 정확한 blocker를 보고한다.
- 각 prompt 의 첫 응답에는 수정 예정 파일, 예상 검증 명령, blocker 후보를 포함한다.

추가 규칙:
- 병렬 worker 검증은 기본적으로 저장소의 도커 테스트 명령을 사용한다.
- 외부 DB 가 필요하면 worktree 별 `.env` 또는 승인된 환경변수만 주입하고, repo 차원의 DB up/down 을 추가하지 않는다.
- `pnpm-lock.yaml` 과 `requirements/lock/py311-dev.txt` 를 재현성 기준으로 삼는다.
