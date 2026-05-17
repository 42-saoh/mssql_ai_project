# Task 0041: SP Operation Model Renewal

## Goal
P41은 `PCO_GU_ManageBond_PRC` 같은 복잡한 Stored Procedure를 단일 DTO skeleton으로
축소하지 않고, 업무 분기별 operation contract와 multi-DTO blueprint로 분리하는 리뉴얼이다.
첫 slice인 P41A는 `SpOperationModel.v0.1` 계약, sanitized fixture, eval gate, 후속 구현
프롬프트를 고정한다.

## Context
- 관련 문서: `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`
- 기준 계약: `spec/eval/p41_sp_operation_model_contract.yaml`
- 기준 fixture: `fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml`
- 기준 대상: `PPM.dbo.PCO_GU_ManageBond_PRC`
- 외부 참고: `D:/migration/test_mcp_server_with_codex/MIGRATION_GUIDE.md`

## In Scope
- `CRUDFlag` `R/A/C/U/D/VENDOR_U/ONLINE_U` 분기별 operation contract 모델링
- statement evidence, branch condition, DTO blueprint, review marker 계약 초안
- 현재 `JavaMyBatisSpWrapperRenderer`의 단일 DTO collapse 한계를 eval로 가시화
- P41B~P41F 순차 구현 프롬프트와 manifest wiring

## Out of Scope
- UI 변경
- 실제 DB row data 조회 또는 Stored Procedure 실행
- business DB DDL/DML 자동 적용
- production generator 전면 교체
- OpenAI SDK dependency 추가 또는 lock 갱신

## Inputs
- 대상 객체: `PPM.dbo.PCO_GU_ManageBond_PRC`
- 참고 guide: `MIGRATION_GUIDE.md` 구조와 품질 목표
- 기존 public artifact contract: `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, `MAPPER_XML`

## Constraints
- `production_ready: false` 유지
- `DTO_DRAFT` artifact type은 유지하되 내부 표현만 multi-file bundle로 확장 가능
- raw SP definition, raw prompt, raw provider response, row data, secret 저장 금지
- 불확실한 TVF/procedure 구분, cross-DB write, called procedure I/O는 `REVIEW_REQUIRED`
- P41은 병렬 없이 `P41A -> P41B -> P41C -> P41D -> P41E -> P41F` 순서로 진행

## Deliverables
- `SpOperationModel.v0.1` domain contract
- `p41_sp_operation_model@0.1.0` eval contract
- `PCO_GU_ManageBond_PRC` sanitized operation fixture
- contract/eval tests
- P41 prompt pack and manifest wiring
- architecture/eval/policy/tool/docs sync

## Verification
- `make test PYTEST_ARGS="tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py"`
- `git diff --check`

## Done Definition
- P41A fixture가 `SpOperationModel.v0.1`로 validate 된다.
- `PCO_GU_ManageBond_PRC` 업무 분기와 최소 9개 DTO blueprint가 표현된다.
- 현재 단일 DTO 생성 방식의 gap이 테스트로 드러난다.
- 후속 P41B~P41F 작업자가 같은 계약과 prompt pack에서 순차적으로 이어갈 수 있다.

## Notes / Risks
- P41A는 generator를 multi-DTO로 바꾸지 않는다. 해당 구현은 P41E에서 수행한다.
- `PCS_PA_ReserveAmtSplitString_PRC`는 TVF/procedure 여부가 불확실하므로 자동 확정하지 않는다.
- ERP cross-DB update는 transaction boundary 검토 전까지 `REVIEW_REQUIRED`다.
