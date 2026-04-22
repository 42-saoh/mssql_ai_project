from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from mssql_mcp_app.settings import LiveMetadataSettings


@dataclass(frozen=True)
class DbProfile:
    id: str
    label: str
    database: str
    purpose: str
    read_only: bool = True
    is_default: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)



def _profile_from_record(record: dict[str, Any], *, default_profile_id: str) -> DbProfile:
    profile_id = str(record.get("id", "")).strip()
    database = str(record.get("database", "")).strip()
    if not profile_id or not database:
        raise ValueError("Each db profile requires non-empty 'id' and 'database'.")

    label = str(record.get("label", profile_id)).strip() or profile_id
    purpose = str(record.get("purpose", "metadata")).strip() or "metadata"

    return DbProfile(
        id=profile_id,
        label=label,
        database=database,
        purpose=purpose,
        read_only=True,
        is_default=profile_id == default_profile_id,
    )



def load_db_profiles(settings: LiveMetadataSettings, *, repo_root: Path | None = None) -> list[DbProfile]:
    repo_base = repo_root or Path.cwd()
    profile_path = (repo_base / settings.profile_file).resolve()

    if profile_path.exists():
        payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        default_profile_id = (
            str(payload.get("defaultProfileId", settings.default_profile_id)).strip()
            or settings.default_profile_id
        )
        records = payload.get("profiles", [])
        if not isinstance(records, list):
            raise ValueError("'profiles' must be a list in the metadata profile file.")
        profiles = [_profile_from_record(item, default_profile_id=default_profile_id) for item in records]
        if profiles:
            return profiles

    return [
        DbProfile(
            id=settings.default_profile_id,
            label=f"Fallback profile ({settings.metadata_db_fallback})",
            database=settings.metadata_db_fallback,
            purpose="fallback",
            read_only=True,
            is_default=True,
        )
    ]



def get_default_profile(profiles: list[DbProfile]) -> DbProfile:
    for profile in profiles:
        if profile.is_default:
            return profile
    if not profiles:
        raise ValueError("At least one db profile must be configured.")
    return profiles[0]
