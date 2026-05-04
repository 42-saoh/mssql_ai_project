# packages/generation

SP 분석 문서, Mapper XML, Service, DTO/VO/Model, DDL 초안 생성기를 둘 자리다.

현재 구현 기준:

- `ai_agent_generation.GenerationContext` 는 fixture/canonical-like 입력을 deterministic renderer 에 전달한다.
- `SPAnalysisDocumentRenderer`, `DependencyReportRenderer`, `JavaMyBatisSpWrapperRenderer` 는 draft-only 산출물을 만든다.
- `JAVA_MYBATIS_DRAFT` 는 OpenAPI requested output group 이므로 persisted artifact enum 을 새로 만들지 않고 DTO/Service/Mapper/Mapper XML draft bundle 로 확장한다.
- 모든 draft 출력은 evidence refs, TODO, `REVIEW_REQUIRED` 경계를 포함해야 한다.
