from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LiveMetadataSettings:
    live_metadata_enabled: bool
    metadata_host: str
    metadata_port: int
    metadata_user: str
    metadata_password: str
    metadata_db_fallback: str
    default_profile_id: str
    profile_file: str
    connect_timeout_seconds: int



def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)



def load_live_metadata_settings() -> LiveMetadataSettings:
    return LiveMetadataSettings(
        live_metadata_enabled=_env_flag("MSSQL_ENABLE_LIVE_METADATA", default=False),
        metadata_host=os.getenv("MSSQL_METADATA_HOST", "").strip(),
        metadata_port=_env_int("MSSQL_METADATA_PORT", 1433),
        metadata_user=os.getenv("MSSQL_METADATA_USER", "").strip(),
        metadata_password=os.getenv("MSSQL_METADATA_PASSWORD", ""),
        metadata_db_fallback=os.getenv("MSSQL_METADATA_DB", "master").strip() or "master",
        default_profile_id=os.getenv("MSSQL_METADATA_DEFAULT_PROFILE_ID", "master").strip()
        or "master",
        profile_file=(
            os.getenv(
                "MSSQL_METADATA_PROFILE_FILE",
                "config/mssql/local_docker_profiles.yaml",
            ).strip()
            or "config/mssql/local_docker_profiles.yaml"
        ),
        connect_timeout_seconds=_env_int("MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS", 5),
    )
