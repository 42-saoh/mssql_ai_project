# packages/domain

공통 계약과 상태 모델을 둔다.

현재 기준:
- DDL v2 와 공유하는 `JobStatus`, `WorkflowStepType`, `ArtifactStatus`, `ArtifactType`
- OpenAPI request `outputs` 용 `RequestedOutputType`
- 사용자-facing requested output 을 persisted artifact type 으로 연결하는 `REQUESTED_OUTPUT_ARTIFACT_TYPES`
