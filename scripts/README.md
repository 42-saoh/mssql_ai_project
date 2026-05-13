여기에는 bootstrap/check/helper 스크립트를 둔다.

추가 스크립트:
- `run_pytest_selection.py` — 선택한 경로 또는 `tests/suites.yaml` 의 `@core` 같은 alias 중 실제 pytest 파일만 골라 실행한다. 도커 테스트 러너에서 빈 디렉터리/placeholder README 로 인한 실패를 줄이기 위한 도우미다.
- `compose_project_name.sh` — 병렬 worktree 별 Docker Compose project name 을 계산한다.
- `resolve_dev_ports.sh` — 병렬 worktree 별 APP/MCP/WEB 포트를 계산한다.
- `install_python_locked.sh` — Python 개발/테스트 의존성을 lock 제약 파일 기준으로 설치한다.
- `install_web_workspace.sh` — `pnpm-lock.yaml` 기준의 web/workspace 설치를 수행하고, 잠금 파일이 없으면 명시적으로 중단한다.
- `win_git_bash.ps1` — Windows PowerShell 에서 Git Bash 를 경유해 `make`/`pnpm` 계열 명령을 실행한다. WinGet Links shim 대신 실제 WinGet package 경로를 PATH 앞에 붙인다.
