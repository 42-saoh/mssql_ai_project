PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.

너는 **통합 검증 / Eval / Docs Sync 트랙 담당**이다.
이 단계는 앞선 트랙의 결과가 병합된 뒤 저장소를 한 번 정리하고, 최소 end-to-end 와 문서 정합성을 맞추는 목적이다.

Role:
- docs_curator
- reviewer

Preferred Skills:
- eval-fixture-authoring
- docs-sync
- browser-automation-smoke

Task:
- 현재 병합된 결과를 기준으로 e2e/eval fixture 를 추가하고, 루트 문서와 운영 문서를 동기화해.
- 구현된 내용과 문서가 어긋나는 부분을 정리하고, follow-up backlog 를 남겨.

In Scope:
- e2e or smoke tests for happy path
- eval fixtures / sample canonical payloads
- docs sync for changed commands, paths, architecture notes
- known gaps / next slices documentation

Out of Scope:
- 대규모 신규 기능 구현
- 계약 대변경
- 실제 배포 자동화

Target Files/Dirs:
- tests/e2e/**
- tests/eval/**
- fixtures/eval/**
- docs/**
- 필요 시 루트 문서

Constraints:
- 신규 구현보다 통합 검증과 정합성 유지에 집중
- 문서에는 실제 구현된 것만 반영
- 남은 TODO 는 숨기지 말고 분리해서 기록

Expected Deliverables:
- e2e/eval assets
- synced docs
- follow-up backlog or known gaps memo

Verification:
- `make test PYTEST_ARGS="tests/e2e tests/eval"`
- 문서와 구현 비교 결과 요약

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Follow-ups
