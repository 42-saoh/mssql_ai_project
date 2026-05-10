PYTHON ?= python
UVICORN ?= uvicorn
RUFF ?= ruff
PNPM ?= pnpm
DOCKER_COMPOSE ?= docker compose
REPO_ROOT ?= $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)
WORKTREE_PATH ?= $(REPO_ROOT)
TEST_COMPOSE_FILE ?= $(REPO_ROOT)/docker/test/docker-compose.yml
PYTEST_ARGS ?=
PYTEST_SELECTION_RUNNER ?= scripts/run_pytest_selection.py
TEST_COMPOSE_PROJECT_PREFIX ?= codex
TEST_COMPOSE_PROJECT_NAME ?= $(shell TEST_COMPOSE_PROJECT_PREFIX="$(TEST_COMPOSE_PROJECT_PREFIX)" WORKTREE_PATH="$(WORKTREE_PATH)" sh "$(REPO_ROOT)/scripts/compose_project_name.sh" 2>/dev/null || echo codex-local)
DOCKER_TEST_ENV = env COMPOSE_PROJECT_NAME="$(TEST_COMPOSE_PROJECT_NAME)" WORKTREE_PATH="$(WORKTREE_PATH)"
PORT_RESOLVER ?= $(REPO_ROOT)/scripts/resolve_dev_ports.sh
APP_PORT ?= $(shell WORKTREE_PATH="$(WORKTREE_PATH)" WORKTREE_PORT_SLOT="$(WORKTREE_PORT_SLOT)" sh "$(PORT_RESOLVER)" APP_PORT 2>/dev/null || echo 8000)
MCP_PORT ?= $(shell WORKTREE_PATH="$(WORKTREE_PATH)" WORKTREE_PORT_SLOT="$(WORKTREE_PORT_SLOT)" sh "$(PORT_RESOLVER)" MCP_PORT 2>/dev/null || echo 8100)
WEB_PORT ?= $(shell WORKTREE_PATH="$(WORKTREE_PATH)" WORKTREE_PORT_SLOT="$(WORKTREE_PORT_SLOT)" sh "$(PORT_RESOLVER)" WEB_PORT 2>/dev/null || echo 3000)
LOCAL_PYTHONPATH ?= $(REPO_ROOT)/apps/api:$(REPO_ROOT)/services/mssql-mcp:$(REPO_ROOT)/packages/domain/src:$(REPO_ROOT)/packages/analysis/src:$(REPO_ROOT)/packages/generation/src:$(REPO_ROOT)/packages/validation/src
PYTHON_LOCK_FILE ?= requirements/lock/py311-dev.txt
PYTHON_INSTALL_SCRIPT ?= $(REPO_ROOT)/scripts/install_python_locked.sh
WEB_INSTALL_SCRIPT ?= $(REPO_ROOT)/scripts/install_web_workspace.sh
ALLOW_UNLOCKED_PNPM_INSTALL ?= 0

.PHONY: setup fmt lint test check run-api run-mcp run-web eval test-build test-web-smoke docker-project-name test-shell test-web-shell test-down test-reset dev-ports

ENV_FILE ?= $(REPO_ROOT)/.env
COMPOSE_ENV_FILE ?= $(if $(wildcard $(ENV_FILE)),--env-file "$(ENV_FILE)",)
LOAD_ENV = set -a; if [ -f "$(ENV_FILE)" ]; then . "$(ENV_FILE)"; fi; set +a

setup:
	env PYTHON="$(PYTHON)" PYTHON_LOCK_FILE="$(PYTHON_LOCK_FILE)" sh "$(PYTHON_INSTALL_SCRIPT)"
	env PNPM="$(PNPM)" ALLOW_UNLOCKED_PNPM_INSTALL="$(ALLOW_UNLOCKED_PNPM_INSTALL)" sh "$(WEB_INSTALL_SCRIPT)"

fmt:
	$(RUFF) format apps/api services/mssql-mcp packages tests scripts

lint:
	$(RUFF) check apps/api services/mssql-mcp packages tests scripts
	$(PYTHON) -m compileall apps/api services/mssql-mcp packages tests

docker-project-name:
	@echo $(TEST_COMPOSE_PROJECT_NAME)

dev-ports:
	@WORKTREE_PATH="$(WORKTREE_PATH)" WORKTREE_PORT_SLOT="$(WORKTREE_PORT_SLOT)" sh "$(PORT_RESOLVER)"

test:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" run --rm python-test sh -lc "env PYTHON=python PYTHON_LOCK_FILE=$(PYTHON_LOCK_FILE) sh scripts/install_python_locked.sh && python $(PYTEST_SELECTION_RUNNER) $(PYTEST_ARGS)"

check: fmt lint test

run-api:
	@$(LOAD_ENV); PYTHONPATH="$(LOCAL_PYTHONPATH)$${PYTHONPATH:+:$$PYTHONPATH}" $(UVICORN) api_app.main:app --app-dir apps/api --reload --port $(APP_PORT)

run-mcp:
	@$(LOAD_ENV); PYTHONPATH="$(LOCAL_PYTHONPATH)$${PYTHONPATH:+:$$PYTHONPATH}" $(UVICORN) mssql_mcp_app.main:app --app-dir services/mssql-mcp --reload --port $(MCP_PORT)

run-web:
	@$(LOAD_ENV); cd apps/web && PORT=$(WEB_PORT) $(PNPM) exec next dev --port $(WEB_PORT)

eval:
	$(MAKE) test PYTEST_ARGS="tests/contract tests/e2e tests/eval"

test-build:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" build python-test web-test

test-web-smoke:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" run --rm web-test sh -lc "env PNPM=pnpm ALLOW_UNLOCKED_PNPM_INSTALL=$(ALLOW_UNLOCKED_PNPM_INSTALL) sh scripts/install_web_workspace.sh && pnpm --dir apps/web test"

test-shell:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" run --rm python-test sh

test-web-shell:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" run --rm web-test sh

test-down:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" down --remove-orphans

test-reset:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) $(COMPOSE_ENV_FILE) -f "$(TEST_COMPOSE_FILE)" down --remove-orphans --volumes
