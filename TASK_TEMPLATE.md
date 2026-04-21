# TASK_TEMPLATE.md

## 목적

이 문서는 Codex 에게 일을 맡길 때 사용할 표준 작업 브리프 템플릿이다.  
작업의 범위, 제약, 산출물, 검증 기준을 한 번에 전달하도록 설계한다.

---

## 1. 작업 브리프 템플릿

```md
# Task
- ID:
- Title:
- Priority:
- Owner:
- Requested by:

## Goal
이번 작업의 최종 목표를 한 문단으로 적는다.

## Context
- 관련 문서:
  - PROJECT.md
  - ARCHITECTURE.md
  - TOOLS.md
  - POLICY.md
  - EVAL_SPEC.md
- 관련 코드/디렉터리:
- 선행 이슈/결정:

## In Scope
- 
- 
- 

## Out of Scope
- 
- 
- 

## Inputs
- 대상 객체:
- 기존 계약:
- 참고 파일:
- 샘플/fixture:

## Constraints
- 정책 제약:
- 성능/보안 제약:
- 변경 가능 디렉터리:
- 금지 사항:
- 스키마 변경 시 `db/schema/` versioned SQL 추가 여부:
- 도커 기반 테스트 경로:

## Deliverables
- 
- 
- 

## Verification
- 실행할 테스트:
- 계약 검증:
- 수동 점검:
- eval/fixture:

## Done Definition
- 
- 
- 

## Notes / Risks
- 가정:
- 오픈 이슈:
- 후속 작업:
```

---

## 2. Codex 프롬프트 템플릿

아래 블록은 Codex CLI 에 그대로 전달하기 좋은 형태다.

```text
PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 기준으로 작업해.

Role:
- architect | platform_worker | mcp_engineer | template_engineer | reviewer | docs_curator

Preferred Skill:
- repo-bootstrap | contract-to-code | mcp-tooling-design | eval-fixture-authoring | quality-gate-review | docs-sync

Task:
- [여기에 작업 요약]

In Scope:
- [항목]
- [항목]

Out of Scope:
- [항목]
- [항목]

Target Files/Dirs:
- [경로]
- [경로]

Constraints:
- 실제 데이터 접근 금지
- 자동 DDL 실행 금지
- 스키마 변경은 `db/schema/` versioned SQL 추가만 허용
- DB 적용/기동/중지는 저장소 밖 수동 절차로 분리
- 승인 없는 파괴적 변경 금지
- 작은 변경 단위 유지
- 문서 동기화 포함

Expected Deliverables:
- [산출물]
- [산출물]

Verification:
- `make test` 또는 동등한 도커 기반 검증
- [추가 테스트/검증]

Report Format:
- 변경 파일
- 핵심 구현 내용
- 검증 결과
- 남은 리스크
```

---

## 3. 작업 분해 템플릿

기능이 큰 경우 아래처럼 단계로 쪼갠다.

```md
## Slice 1
- 목적:
- 변경 범위:
- 검증:
- 완료 조건:

## Slice 2
- 목적:
- 변경 범위:
- 검증:
- 완료 조건:

## Slice 3
- 목적:
- 변경 범위:
- 검증:
- 완료 조건:
```

---

## 4. 리뷰 요청 템플릿

```text
reviewer 역할로 검토해.
다음에 집중해:
1. correctness
2. policy compliance
3. missing tests
4. docs drift
5. unsafe assumptions

반드시 아래 형식으로 답해:
- Findings
- Severity
- Repro steps / rationale
- Suggested fix
- Residual risk
```

---

## 5. 문서 동기화 요청 템플릿

```text
docs_curator 역할과 docs-sync skill 을 사용해.
다음 변경을 문서에 반영해:
- [구조/API/명령/정책 변경]

업데이트 대상:
- AGENTS.md
- ARCHITECTURE.md
- TOOLS.md
- POLICY.md
- EVAL_SPEC.md

문서와 코드가 모순되지 않게 최소 수정으로 맞춰.
```
