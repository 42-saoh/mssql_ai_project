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

.PHONY: setup fmt lint test check run-api run-mcp run-web eval test-build test-web-smoke docker-project-name test-shell test-web-shell test-down test-reset

setup:
	@echo "Install Python deps: $(PYTHON) -m pip install -e .[dev]"
	@echo "Install web deps: cd apps/web && $(PNPM) install"

fmt:
	$(RUFF) format apps/api services/mssql-mcp packages tests scripts

lint:
	$(RUFF) check apps/api services/mssql-mcp packages tests scripts
	$(PYTHON) -m compileall apps/api services/mssql-mcp packages tests

docker-project-name:
	@echo $(TEST_COMPOSE_PROJECT_NAME)

test:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" run --rm python-test sh -lc "python -m pip install -e .[dev] && python $(PYTEST_SELECTION_RUNNER) $(PYTEST_ARGS)"

check: fmt lint test

run-api:
	$(UVICORN) api_app.main:app --app-dir apps/api --reload --port 8000

run-mcp:
	$(UVICORN) mssql_mcp_app.main:app --app-dir services/mssql-mcp --reload --port 8100

run-web:
	cd apps/web && $(PNPM) dev

eval:
	$(MAKE) test PYTEST_ARGS="tests/contract tests/e2e tests/eval"

test-build:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" build python-test web-test

test-web-smoke:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" run --rm web-test sh -lc "pnpm install --no-frozen-lockfile && pnpm --dir apps/web test"

test-shell:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" run --rm python-test sh

test-web-shell:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" run --rm web-test sh

test-down:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" down --remove-orphans

test-reset:
	$(DOCKER_TEST_ENV) $(DOCKER_COMPOSE) -f "$(TEST_COMPOSE_FILE)" down --remove-orphans --volumes
