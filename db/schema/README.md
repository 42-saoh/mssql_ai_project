# db/schema

이 디렉터리는 플랫폼 DB 스키마 변경을 **버전 업 SQL 파일**로 관리한다.

원칙:
- 현재 기준 스키마는 `ai_agent_platform_schema_v2_dbo_prefix.sql` 이다.
- 이후 변경은 `V000x__description.sql` 또는 팀이 합의한 버전 규칙으로 새 파일을 추가한다.
- 저장소와 Codex 는 이 SQL 을 실제 DB 에 자동 적용하지 않는다.
- 실제 반영은 사용자가 외부 DB 환경에 수동으로 수행한다.
