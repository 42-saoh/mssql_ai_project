# packages/domain

공통 계약과 상태 모델을 둔다.

현재 기준:
- DDL v2 와 공유하는 `JobStatus`, `WorkflowStepType`, `ArtifactStatus`, `ArtifactType`
- OpenAPI request `outputs` 용 `RequestedOutputType`
- 사용자-facing requested output 을 persisted artifact type 으로 연결하는 `REQUESTED_OUTPUT_ARTIFACT_TYPES`
- `CanonicalAnalysisModel.v2` 계약: 기존 SP 중심 snapshot id, registry version refs,
  procedure/dependency/pattern/result-set/call-graph/business-rule/modernization/evidence refs 를
  유지하면서 `analysisSubject`, `metadataProfiles`, `dependencyEvidence`, `dtoReadiness`,
  `factGraph`, `knowledgeAssetRefs` 를 추가한다.
- `SpOperationModel.v0.1` 계약: P41에서 복잡한 SP의 branch-level operation, sanitized
  statement evidence, DTO blueprint 를 Java/MyBatis 생성 전 단계로 분리한다. 이 계약은
  internal planning 용도이며 public artifact type 또는 production readiness 를 바꾸지 않는다.
