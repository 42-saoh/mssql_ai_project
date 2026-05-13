from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition
from typing import Iterator

from mssql_mcp_app.errors import MCP_BACKPRESSURE, MetadataToolError


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class _AdmissionCounter:
    active: int = 0
    condition: Condition = Condition()

    @contextmanager
    def acquire(
        self,
        *,
        max_active: int,
        wait_ms: int,
        error: MetadataToolError,
    ) -> Iterator[None]:
        acquired = False
        if max_active <= 0:
            yield
            return
        deadline = time.monotonic() + max(wait_ms, 0) / 1000
        with self.condition:
            while self.active >= max_active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise error
                self.condition.wait(timeout=min(remaining, 0.05))
            self.active += 1
            acquired = True
        try:
            yield
        finally:
            if acquired:
                with self.condition:
                    self.active = max(self.active - 1, 0)
                    self.condition.notify()


_METADATA_ADMISSION = _AdmissionCounter()


@contextmanager
def metadata_admission(*, tool_name: str, db_profile_id: str) -> Iterator[None]:
    max_active = _env_int("MSSQL_METADATA_MAX_CONCURRENCY", 4)
    wait_ms = _env_int("BACKPRESSURE_WAIT_MS", 250)
    error = MetadataToolError(
        MCP_BACKPRESSURE,
        "MSSQL metadata tool capacity is currently exhausted.",
        {
            "toolName": tool_name,
            "dbProfileId": db_profile_id,
            "maxActive": max_active,
            "waitMs": wait_ms,
        },
    )
    with _METADATA_ADMISSION.acquire(
        max_active=max_active,
        wait_ms=wait_ms,
        error=error,
    ):
        yield
