from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


UNKNOWN_TOOL = "UNKNOWN_TOOL"
INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
READ_ONLY_VIOLATION = "READ_ONLY_VIOLATION"
LIVE_METADATA_UNAVAILABLE = "LIVE_METADATA_UNAVAILABLE"
INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS = {
    UNKNOWN_TOOL: 404,
    INVALID_ARGUMENTS: 400,
    PROFILE_NOT_FOUND: 404,
    OBJECT_NOT_FOUND: 404,
    READ_ONLY_VIOLATION: 403,
    LIVE_METADATA_UNAVAILABLE: 503,
    INTERNAL_ERROR: 500,
}


@dataclass
class MetadataToolError(RuntimeError):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def http_status(self) -> int:
        return ERROR_STATUS.get(self.code, 500)
