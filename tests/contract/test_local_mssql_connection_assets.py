from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]



def test_local_docker_profile_registry_exists() -> None:
    registry = REPO_ROOT / "config" / "mssql" / "local_docker_profiles.yaml"
    assert registry.exists(), "local MSSQL profile registry should exist"
    payload = yaml.safe_load(registry.read_text(encoding="utf-8"))
    assert payload.get("defaultProfileId", "master") == "master"
    assert any(profile["database"] == "master" for profile in payload["profiles"])
    assert any(profile["database"] == "PLF" for profile in payload["profiles"])
    assert any(
        profile["id"] == "ppm" and profile["database"] == "PPM"
        for profile in payload["profiles"]
    )



def test_docker_test_compose_forwards_local_mssql_env() -> None:
    compose_text = (REPO_ROOT / "docker" / "test" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "host.docker.internal:host-gateway" in compose_text
    assert "PLATFORM_DB_HOST" in compose_text
    assert "MSSQL_METADATA_HOST" in compose_text
    assert "MSSQL_METADATA_PROFILE_FILE" in compose_text
    assert "MSSQL_METADATA_TDS_VERSION" in compose_text


def test_makefile_docker_targets_load_local_env_file_when_present() -> None:
    makefile_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ENV_FILE ?= $(REPO_ROOT)/.env" in makefile_text
    assert "COMPOSE_ENV_FILE ?" in makefile_text
    assert '--env-file "$(ENV_FILE)"' in makefile_text

    docker_targets = (
        "test:",
        "test-build:",
        "test-web-smoke:",
        "test-shell:",
        "test-web-shell:",
        "test-down:",
        "test-reset:",
    )
    for target in docker_targets:
        target_start = makefile_text.index(target)
        next_target_start = makefile_text.find("\n\n", target_start)
        target_block = makefile_text[target_start:next_target_start]
        assert "$(COMPOSE_ENV_FILE) -f" in target_block
