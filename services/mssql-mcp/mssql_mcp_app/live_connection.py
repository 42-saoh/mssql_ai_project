from __future__ import annotations

from typing import Any

from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.settings import LiveMetadataSettings


class MetadataConnectionError(RuntimeError):
    """Raised when the optional live metadata connection cannot be established."""



def _validate_live_settings(settings: LiveMetadataSettings) -> None:
    missing: list[str] = []
    if not settings.metadata_host:
        missing.append("MSSQL_METADATA_HOST")
    if not settings.metadata_user:
        missing.append("MSSQL_METADATA_USER")
    if not settings.metadata_password:
        missing.append("MSSQL_METADATA_PASSWORD")
    if missing:
        raise MetadataConnectionError(
            "Missing live metadata configuration: " + ", ".join(missing)
        )



def probe_profile_connection(
    profile: DbProfile,
    settings: LiveMetadataSettings,
) -> dict[str, Any]:
    _validate_live_settings(settings)

    try:
        import pytds
    except Exception as exc:  # pragma: no cover - dependency/runtime issue
        raise MetadataConnectionError(
            "python-tds is required for live MSSQL metadata connectivity."
        ) from exc

    try:
        connection = pytds.connect(
            dsn=settings.metadata_host,
            port=settings.metadata_port,
            database=profile.database,
            user=settings.metadata_user,
            password=settings.metadata_password,
            login_timeout=settings.connect_timeout_seconds,
            timeout=settings.connect_timeout_seconds,
            tds_version=settings.metadata_tds_version,
            readonly=True,
            autocommit=True,
            appname="mssql-mcp-readiness",
            use_mars=False,
        )
        connection.close()
    except Exception as exc:  # pragma: no cover - requires live SQL Server
        raise MetadataConnectionError(str(exc)) from exc

    return {
        "checked": True,
        "connection": "ok",
        "profileId": profile.id,
        "database": profile.database,
        "host": settings.metadata_host,
        "port": settings.metadata_port,
        "readOnlyRequested": True,
    }
