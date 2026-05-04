from __future__ import annotations

from api_app.metadata_service import list_safe_metadata_profiles, list_safe_metadata_tools
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/metadata", tags=["metadata"])


@router.get("/db-profiles")
def list_metadata_profiles() -> dict:
    default_profile_id, profiles = list_safe_metadata_profiles()
    return {
        "defaultProfileId": default_profile_id,
        "profiles": [profile.to_response() for profile in profiles],
    }


@router.get("/tools")
def list_metadata_tools() -> dict:
    return {
        "tools": [tool.to_response() for tool in list_safe_metadata_tools()],
    }
