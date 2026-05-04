from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ToolResponse(BaseModel):
    ok: bool
    toolName: str
    dbProfileId: str | None = None
    snapshotId: str | None = None
    collectedAt: str | None = None
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] | None = None
    error: ToolErrorPayload | None = None
