from pathlib import Path


def test_parallel_docker_assets_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "scripts" / "compose_project_name.sh").exists()

    makefile = (root / "Makefile").read_text(encoding="utf-8")
    assert "TEST_COMPOSE_PROJECT_NAME" in makefile
    assert "docker-project-name" in makefile
    assert "test-down" in makefile
    assert "test-reset" in makefile

    compose = (root / "docker" / "test" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "WORKTREE_PATH" in compose
    assert "type: bind" in compose

    runbook = (root / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md").read_text(encoding="utf-8")
    assert "make docker-project-name" in runbook
    assert "WORKTREE_PATH=/abs/path/to/worktree make test" in runbook
