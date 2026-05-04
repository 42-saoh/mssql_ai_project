from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]



def test_local_docker_profile_registry_exists() -> None:
    registry = REPO_ROOT / "config" / "mssql" / "local_docker_profiles.yaml"
    assert registry.exists(), "local MSSQL profile registry should exist"
    payload = yaml.safe_load(registry.read_text(encoding="utf-8"))
    assert payload["defaultProfileId"] == "master"
    assert any(profile["database"] == "master" for profile in payload["profiles"])
    assert any(profile["database"] == "PLF" for profile in payload["profiles"])
    assert any(profile["id"] == "ppm" and profile["database"] == "PPM" for profile in payload["profiles"])



def test_docker_test_compose_forwards_local_mssql_env() -> None:
    compose_text = (REPO_ROOT / "docker" / "test" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "host.docker.internal:host-gateway" in compose_text
    assert "PLATFORM_DB_HOST" in compose_text
    assert "MSSQL_METADATA_HOST" in compose_text
    assert "MSSQL_METADATA_PROFILE_FILE" in compose_text
