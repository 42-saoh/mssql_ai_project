# Codex Parallel Request Pack

이 디렉터리는 **로컬 Codex CLI 병렬 개발**을 위한 운영 패키지다.
현재 기준은 저장소의 OpenAPI skeleton, Platform DB DDL draft, MCP catalog, validation rules, policy files, `.env.example`, Python/Web lockfile 을 먼저 읽고 각 트랙이 자기 경로만 구현하는 방식이다.

구성:
- `PARALLEL_REQUEST_PLAN.md` — 병렬 개발 웨이브, 트랙, 의존성, 병합 순서
- `PARALLEL_RUNBOOK.md` — worktree 기반 로컬 실행 절차
- `REQUEST_MANIFEST.yaml` — 트랙별 메타데이터, 담당 경로, 프롬프트 매핑
- `prompts/*.md` — Codex 세션에 넣을 수 있는 요청 프롬프트

권장 사용 순서:
1. `PARALLEL_REQUEST_PLAN.md` 읽기
2. `PARALLEL_RUNBOOK.md` 기준으로 worktree 준비
3. `.env.example` 을 `.env` 로 복사하고 로컬 secret 은 커밋하지 않기
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
- `pnpm-lock.yaml` 과 `requirements/lock/py314-dev.txt` 를 재현성 기준으로 삼는다.


## P07 이후 Productization Prompt Pack

P08A~P16은 기존 P00~P07 starter/MVP 병렬 개발 철학을 유지하면서 productization으로 전환하기 위한 후속 prompt pack이다.

P08 산출물:

- `docs/productization-architecture-gap-analysis.md` — starter/MVP 상태, contract drift, PPM readiness 해석
- `PRODUCTIZATION_RELEASE_BACKLOG.md` — P09~P16 worker scope, acceptance criteria, verification, blocker 기준
- `fixtures/eval/productization_readiness_v1.yaml` — PPM pilot manifest 를 eval/demo/readiness gate 에 연결하는 metadata-only fixture

추가 프롬프트:

- `prompts/08a_ppm_pilot_object_discovery_selection.md`
- `prompts/08_product_architecture_release_backlog.md`
- `prompts/09_api_workflow_productization.md`
- `prompts/10_mssql_mcp_productization.md`
- `prompts/11_sp_analysis_evidence_engine.md`
- `prompts/12_java_mybatis_generation_factory.md`
- `prompts/13_validation_approval_audit.md`
- `prompts/14_web_product_ui.md`
- `prompts/15_eval_observability_security_ops.md`
- `prompts/16_pilot_release_readiness.md`

DB 역할은 `PLF = platform DB`, `PPM = pilot analysis target DB` 로 고정한다. PPM이 없거나 live metadata 권한이 없으면 PLF로 대체하지 않고 blocker로 보고한다. P08A가 만든 `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` 은 이후 worker가 공통으로 참조한다. 이 manifest가 `template_only` 상태이면 worker는 실제 object 이름을 임의로 만들지 않는다.

## P17 Live Pilot Blocker Closure Prompt Pack

P16이 `NO_GO`인 경우에는 P17A~P17D를 순차 실행한다.

- `prompts/17a_dependency_metadata_evidence_closure.md` — `DEPENDENCY_METADATA_INCOMPLETE` 해소를 위한 metadata-only dependency evidence 보강
- `prompts/17b_live_artifact_validation_closure.md` — confirmed pilot object set 기준 draft-only artifact validation closure
- `prompts/17c_draft_quality_audit_binding.md` — draft-quality audit evidence binding
- `prompts/17d_pilot_release_go_decision.md` — hard-live 재검증 및 `NO_GO`/`CONDITIONAL_GO` 최종 판정

P17 기준 문서는 `docs/live-pilot-blocker-closure-plan.md`, machine-readable fixture는 `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml` 이다. P17도 PPM을 PLF로 대체하지 않으며, 전체 플랫폼 production-ready 선언은 금지한다.

## P18 Productization Gap Closure Prompt Pack

P17D 이후 scoped live pilot candidate 가 `CONDITIONAL_GO` 여도 production-ready 는 아니다.
P18은 남은 productization gap 을 닫거나 future hardening/deferred item 으로 명확히 분류한다.

- `prompts/18a_canonical_analysis_model_closure.md` — full `CanonicalAnalysisModel` contract closure 또는 정확한 domain blocker 기록
- `prompts/18b_web_http_auth_rbac_evidence.md` — web HTTP adapter release smoke 와 production auth/RBAC evidence/deferred hardening 정리

P18 기준 fixture는 `fixtures/eval/productization_gap_closure_p18_v1.yaml` 이다. P18도 row data,
procedure execution, raw definition text 저장, 자동 DDL/DML, PLF fallback, 승인 없는
publish/export, fake production auth/RBAC 를 허용하지 않는다.
