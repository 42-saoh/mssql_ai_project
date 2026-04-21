# apps/api

중앙 통합형 Agent 플랫폼의 API/BFF, workflow, approval 시작점을 두는 디렉터리다.

## 현재 포함

- `api_app/main.py`
- `api_app/routes/health.py`
- `api_app/routes/jobs.py`
- `api_app/routes/requests.py`

## 다음 구현 우선순위

1. request → job → artifact 흐름 연결
2. registry version binding
3. validation / approval endpoints
4. persistence adapter 연결
