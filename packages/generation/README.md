# packages/generation

P24C/P24 v0.3 status: `SP_ANALYSIS_DOC` and `DEPENDENCY_REPORT` render fixture-first SP
migration guide sections from `GenerationContext.request["migrationGuide"]`
sanitized facts and evidence refs. The user-facing guide uses Korean headings,
stable hidden section anchors, and overview/feature/dependency/DML/phase tables.
`evaluate_p24_migration_guide_quality` scores
the rendered artifact pair and returns only the P24 report fields while keeping
`productionReady: false`.

SP 분석 문서, Mapper XML, Service, DTO/VO/Model, DDL 초안 생성기를 둘 자리다.

현재 구현 기준:

- `ai_agent_generation.GenerationContext` 는 fixture/canonical-like 입력을 deterministic renderer 에 전달한다.
- `SPAnalysisDocumentRenderer`, `DependencyReportRenderer`, `JavaMyBatisSpWrapperRenderer` 는 draft-only 산출물을 만든다.
- `JAVA_MYBATIS_DRAFT` 는 OpenAPI requested output group 이므로 persisted artifact enum 을 새로 만들지 않고 DTO/Service/Mapper/Mapper XML draft bundle 로 확장한다.
- `DTO_MODEL_DRAFT` 는 persisted enum 추가 없이 DTO/VO/Model draft bundle 로 렌더링한다.
- Java/MyBatis naming, package, mapper XML path, namespace, SQL id, field/type mapping 은 `spec/policy/project_ai_java_mybatis_generation_policy.yaml` 을 읽어 적용한다.
- template version, requested output type, output role 은 `packages/templates/artifacts/java_mybatis_registry.yaml` 에서 읽어 manifest 에 기록한다.
- renderer 의 requested output type 과 template registry 의 `requestedOutputType` 이 다르면 contract drift 로 보고 렌더링을 차단한다.
- 모든 draft 출력은 evidence refs, TODO, `REVIEW_REQUIRED` 경계를 포함해야 한다.
- manifest 는 sanitized input snapshot hash, policy/template/generator version, draft lifecycle, generated file inventory, diff/review checklist, SQL risk marker 를 포함한다.
- PPM object-name golden 은 field/parameter/result-shape metadata evidence 가 충분할 때만 추가한다. P17B live pilot artifact manifest 는 selected PPM object/evidence refs 만 고정하며, 없는 컬럼/파라미터/결과 형태를 추론해서 Java/MyBatis golden source 로 만들지 않는다.
