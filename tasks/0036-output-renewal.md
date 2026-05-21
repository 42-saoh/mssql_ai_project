# Task 0036: Output Renewal

## 1. Objective

P36은 기존 산출물 9종 계약을 깨고 최종 산출물 6종 계약으로 재정의한다. SP 분석 문서는 `MIGRATION_GUIDE.md`와 같은 흐름을 따르고, 의존성 보고서는 근거 보고서로 재정의하며, Java/MyBatis 산출물은 단순 SP wrapper가 아니라 근거형 업무 로직 재구성 초안으로 생성한다.

## 2. Scope

- Public requested output/API/UI/validation/generation 흐름에서 `DTO_MODEL_DRAFT`, `DDL_DRAFT`, `VO_DRAFT`, `MODEL_DRAFT`, `DDL_DRAFT`를 제거한다.
- 최종 artifact type은 `SP_ANALYSIS_DOC`, `DEPENDENCY_REPORT`, `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, `MAPPER_XML`만 유지한다.
- `SP_ANALYSIS_DOC`는 `SP 개요`, `의존성 인벤토리`, `DML 영향도 매트릭스`, `호출 흐름`, `복잡도 분석`, `Appendix` 순서를 따른다.
- `DEPENDENCY_REPORT`는 SP 분석 및 Java/MyBatis 생성 근거, bounded sanitized SQL statement evidence, caveat, next evidence를 담는다.
- Java/MyBatis 4개 산출물은 `spRebuild` 또는 `evidenceReconstructed` 모드로 evidence-backed draft를 생성한다.

## 3. Out Of Scope

- 운영 DB row data 조회
- 프로시저 실행
- business DB DDL/DML 자동 실행
- 생성된 Java/MyBatis 코드 자동 반영 또는 배포
- full SP definition 저장
- production-ready 주장

## 4. Required Sequence

1. P36A: 계약, 작업 브리프, 프롬프트 팩, 순차 매니페스트, 계약 테스트 추가
2. P36B: public contract cleanup 및 v9 manual DB CHECK SQL 추가
3. P36C: MIGRATION_GUIDE-style SP 분석 렌더러와 evidence dossier 렌더러 구현
4. P36D: business-logic-aware Java/MyBatis 렌더러 구현
5. P36E: API/Web/docs/eval/golden/readiness 동기화 및 quality gate

## 5. Acceptance Criteria

- P36 계약과 프롬프트 자산이 저장소에서 검증 가능하다.
- 제거 대상 산출물은 public 요청/API/UI/검증/생성 경로에서 노출되지 않는다.
- SP 분석 문서는 `MIGRATION_GUIDE.md`의 6개 상위 흐름을 따른다.
- 의존성 보고서는 dependency-only가 아닌 근거 보고서로 생성된다.
- DTO/Service/Mapper/MapperSQL은 업무 분기, DML, result shape 후보, evidence ref, `REVIEW_REQUIRED` caveat를 포함한다.
- 관련 contract/unit/eval/web smoke 테스트가 갱신된다.
- `production_ready: false`와 승인 게이트 원칙이 문서와 계약에 남아 있다.

## 6. Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p36_output_renewal_contract_prompt_assets.py"
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/eval/test_p36_output_renewal_quality.py tests/unit/generation tests/contract/test_generation_goldens_and_repro_assets.py"
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_openapi_and_env_sample_assets.py tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/unit/web/test_p14_product_ui_static.py"
```

## 7. Reporting

완료 보고에는 바뀐 파일, 구현한 산출물 계약 변화, 검증 명령과 결과, 남은 리스크/TODO를 포함한다.
