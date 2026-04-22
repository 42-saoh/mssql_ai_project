# fixtures/generation

이 디렉터리는 generation/validation 코어의 fixture 와 golden sample 을 둔다.

현재 포함:
- `golden/java_mybatis_sp_wrapper_order_request_v1/` — Java/MyBatis `spWrapper` 기준선 샘플

사용 목적:
- `spec/policy/project_ai_java_mybatis_generation_policy.yaml` 의 출력 구조를 concrete example 로 고정
- P03 생성기/검증기가 evidence, TODO, review checklist 를 빠뜨리지 않도록 회귀 기준 제공
- P05 이후 API/artifact preview 에서도 동일한 예시를 재사용 가능
