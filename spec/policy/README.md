# spec/policy

이 디렉터리는 프로젝트의 **기계 판독형 정책/규칙 자산**을 저장한다.
기존 루트 문서(`PROJECT.md`, `POLICY.md`, `ARCHITECTURE.md`, `AGENTS.md`)를 대체하지 않고,
생성기·표준화 로직·검증 로직이 참조할 수 있는 **추가 기준**으로 사용한다.

## 포함 파일

- `project_ai_java_mybatis_generation_policy.yaml`
  - Java/MyBatis 코드 초안 생성 기준
  - generation mode, naming, package, method pattern, MyBatis 경로/namespace 규칙,
    evidence/TODO/review checklist 를 정의한다.
- `platform_db_standardization_rules_for_ai.json`
  - 플랫폼 DB 표준화 및 메타데이터 활용 기준
  - 표준명/표준타입, actual/standard pair, 약어, 물리명 규칙, 설명 추론 상태,
    DDL draft 및 metadata response 계약을 정의한다.

## 적용 우선순위

충돌이 있을 때는 아래 순서를 따른다.

1. 현재 사용자의 명시적 요청
2. 프로젝트 기준 문서와 이미 확정된 저장소 자산
3. 이 디렉터리의 정책/규칙 파일
4. 레거시 물리 스키마 또는 비표준 관행

## 적용 방식

- 기존 문서와 자산은 **수정 없이 유지**한다.
- 새 정책은 향후 generator/validator/metadata standardization 구현에서 참조하는 보강 규칙으로 사용한다.
- 이미 확정된 현재 저장소 자산(예: 기존 Platform DDL 네이밍)은 자동으로 소급 변경하지 않는다.
- 실제 DB 조회/수정, 자동 DDL 실행, 무검증 자동 반영 금지 원칙은 계속 유지한다.

## 구현 가이드

### Java/MyBatis 생성

- 생성 결과는 항상 draft 로 취급한다.
- evidence, assumption, TODO, review checklist 를 함께 남긴다.
- `metadataCrud`, `spWrapper`, `spRebuild`, `metadataObject` 중 generation mode 를 명시한다.
- 확인되지 않은 프레임워크/공통 컴포넌트는 가정하지 않고 TODO 로 남긴다.

### 플랫폼 DB / 메타데이터 표준화

- actual name/type 과 standard name/type 을 구분해 관리한다.
- 동일 의미는 동일 표준명/표준타입으로 정규화한다.
- 승인되지 않은 약어는 만들지 않는다.
- 설명이 불충분하면 확정 사실처럼 단정하지 않고 `INFERRED_DESCRIPTION` 또는 `REVIEW_REQUIRED` 로 남긴다.

## 검증

이 디렉터리의 핵심 정책 파일은 계약 테스트에서 파싱 가능성과 주요 보호 규칙을 확인한다.
