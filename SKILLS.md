# SKILLS.md

이 저장소는 repo-scoped skills 를 `.agents/skills` 에 둔다.  
각 스킬은 한 가지 작업에 집중하며, Codex가 명시적으로 호출하거나 설명과 일치할 때 선택적으로 사용할 수 있다.

## 사용 가능한 스킬

| 스킬 | 위치 | 언제 쓰는가 | 산출물 |
|---|---|---|---|
| `repo-bootstrap` | `.agents/skills/repo-bootstrap` | 저장소 초기 구조, 루트 문서, Codex 설정, 품질 명령을 세팅할 때 | 저장소 뼈대, 기본 문서, 설정 |
| `contract-to-code` | `.agents/skills/contract-to-code` | 설계 문서나 OpenAPI/DDL을 실제 구현 슬라이스로 옮길 때 | 구현 계획, 코드, 테스트 |
| `mcp-tooling-design` | `.agents/skills/mcp-tooling-design` | MSSQL Metadata MCP tools, schema, errors, contract tests를 설계/구현할 때 | MCP tool spec, adapters, tests |
| `eval-fixture-authoring` | `.agents/skills/eval-fixture-authoring` | fixture, eval dataset, rubric, reproducibility tests를 만들 때 | fixtures, eval runners, reports |
| `quality-gate-review` | `.agents/skills/quality-gate-review` | PR 전 점검, validation rule, approval gate를 검토할 때 | 리뷰 결과, 개선 포인트 |
| `docs-sync` | `.agents/skills/docs-sync` | 코드/계약/정책 변경 이후 문서를 맞출 때 | 문서 업데이트, changelog 요약 |
| `context7-docs` | `.agents/skills/context7-docs` | 최신 프레임워크/라이브러리 문서가 필요한 구현/설정 작업일 때 | 좁은 범위의 문서 근거와 구현 가이드 |
| `browser-automation-smoke` | `.agents/skills/browser-automation-smoke` | 로컬 UI happy-path 확인, 스크린샷, 비파괴적 smoke 검증이 필요할 때 | 검증 로그, 스크린샷, blocker 메모 |
| `framework-adapter-pilot` | `.agents/skills/framework-adapter-pilot` | P43F `pilot` 이후 실제 framework 후보를 내부 adapter 뒤에서 검토할 때 | pilot slice plan, rollback evidence, A/B replay notes |
| `framework-trace-policy-review` | `.agents/skills/framework-trace-policy-review` | framework tool context, trace, persistence, checkpointer 저장 정책을 검토할 때 | trace policy findings, blocker report |
| `orchestration-migration-planning` | `.agents/skills/orchestration-migration-planning` | 대전환을 P44+ 작은 orchestration/framework migration slice로 나눌 때 | reversible migration plan, decision gate checklist |

## 스킬 작성 원칙

- 좁고 명확한 trigger 를 가진다.
- 입력, 단계, 산출물, 실패 조건이 드러나야 한다.
- 스크립트가 없어도 재사용 가능해야 한다.
- 정책 위반 가능성이 있는 작업은 명시적으로 차단한다.
- 문서 스킬은 중복 생성보다 기존 문서 갱신을 우선한다.

## 운영 규칙

- 스킬이 너무 커지면 역할별로 분리한다.
- 동일한 작업을 반복해서 요청하게 되면 스킬로 승격한다.
- 불필요해진 스킬은 제거하거나 보관 처리한다.

## Post-P43 Framework Readiness Skills

| Skill | Location | When to use | Output |
|---|---|---|---|
| `framework-adapter-pilot` | `.agents/skills/framework-adapter-pilot` | OpenAI Agents SDK, LangGraph, or another candidate must be evaluated behind `AiGenerationFrameworkAdapter.v0.1` | adapter pilot plan, fake-first replay evidence, rollback notes |
| `framework-trace-policy-review` | `.agents/skills/framework-trace-policy-review` | Candidate traces, tool context, persistence, or checkpointers could store sensitive payloads | sanitized trace review, blocker ids, residual `REVIEW_REQUIRED` |
| `orchestration-migration-planning` | `.agents/skills/orchestration-migration-planning` | A large workflow/runtime migration needs to be split into reversible P44+ slices | migration slice order, tests, docs decision gate |

Post-P43 framework work keeps `production_ready: false`, uses `.agents/skills` rather than a new `.agent` directory, and preserves the current Responses/httpx gateway or baseline adapter as rollback until a separate decision gate approves more.
## P42 Additional Skills

| Skill | Location | When to use | Output |
|---|---|---|---|
| `ai-draft-pack-authoring` | `.agents/skills/ai-draft-pack-authoring` | P42 `AiJavaMyBatisDraftPack.v0.1` file inventory/content/repair 를 작성할 때 | AI Draft Pack inventory, Java/MyBatis draft pack, repair notes |
| `java-mybatis-draft-validator` | `.agents/skills/java-mybatis-draft-validator` | DTO/Service/Mapper/MapperXML 초안의 blank, fallback, single DTO collapse, forbidden marker 를 검증할 때 | blocker report, review marker report, validation checklist |
| `sp-business-logic-migration-eval` | `.agents/skills/sp-business-logic-migration-eval` | `MIGRATION_GUIDE.md`와 생성 산출물을 비교해 SP business branch 품질을 평가할 때 | branch coverage report, DTO/method responsibility map, missing `REVIEW_REQUIRED` findings |

P42/P43 domain skills treat ManageBond as benchmark evidence only, not as production-runtime hardcoding.
