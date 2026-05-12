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
    metadata_tds_version: int = 1946157060
    default_profile_id_from_env: bool = False



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


_TDS_VERSION_VALUES = {
    "70": 1879048192,
    "tds70": 1879048192,
    "71": 1895825408,
    "tds71": 1895825408,
    "72": 1913192450,
    "tds72": 1913192450,
    "73": 1930035203,
    "tds73": 1930035203,
    "74": 1946157060,
    "tds74": 1946157060,
}


def _env_tds_version(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower().replace(".", "").replace("_", "")
    if normalized in _TDS_VERSION_VALUES:
        return _TDS_VERSION_VALUES[normalized]
    return int(value)



def load_live_metadata_settings() -> LiveMetadataSettings:
    default_profile_id_value = os.getenv("MSSQL_METADATA_DEFAULT_PROFILE_ID")
    return LiveMetadataSettings(
        live_metadata_enabled=_env_flag("MSSQL_ENABLE_LIVE_METADATA", default=False),
        metadata_host=os.getenv("MSSQL_METADATA_HOST", "").strip(),
        metadata_port=_env_int("MSSQL_METADATA_PORT", 1433),
        metadata_user=os.getenv("MSSQL_METADATA_USER", "").strip(),
        metadata_password=os.getenv("MSSQL_METADATA_PASSWORD", ""),
        metadata_db_fallback=os.getenv("MSSQL_METADATA_DB", "master").strip() or "master",
        default_profile_id=(default_profile_id_value or "master").strip() or "master",
        profile_file=(
            os.getenv(
                "MSSQL_METADATA_PROFILE_FILE",
                "config/mssql/local_docker_profiles.yaml",
            ).strip()
            or "config/mssql/local_docker_profiles.yaml"
        ),
        connect_timeout_seconds=_env_int("MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS", 5),
        metadata_tds_version=_env_tds_version(
            "MSSQL_METADATA_TDS_VERSION",
            1946157060,
        ),
        default_profile_id_from_env=bool(
            default_profile_id_value is not None and default_profile_id_value.strip()
        ),
    )
