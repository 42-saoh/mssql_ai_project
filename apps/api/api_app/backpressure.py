from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition
from typing import Iterator


WORKFLOW_BACKPRESSURE = "WORKFLOW_BACKPRESSURE"


class WorkflowBackpressureError(RuntimeError):
    code = WORKFLOW_BACKPRESSURE

    def __init__(self, *, max_active: int, wait_ms: int) -> None:
        super().__init__("Workflow capacity is currently exhausted.")
        self.max_active = max_active
        self.wait_ms = wait_ms


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
    def acquire(self, *, max_active: int, wait_ms: int) -> Iterator[None]:
        acquired = False
        if max_active <= 0:
            yield
            return
        deadline = time.monotonic() + max(wait_ms, 0) / 1000
        with self.condition:
            while self.active >= max_active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkflowBackpressureError(
                        max_active=max_active,
                        wait_ms=wait_ms,
                    )
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


_WORKFLOW_ADMISSION = _AdmissionCounter()


@contextmanager
def workflow_admission() -> Iterator[None]:
    max_active = _env_int("WORKFLOW_MAX_ACTIVE_JOBS", 4)
    wait_ms = _env_int("BACKPRESSURE_WAIT_MS", 250)
    with _WORKFLOW_ADMISSION.acquire(max_active=max_active, wait_ms=wait_ms):
        yield


def workflow_limit_summary() -> dict[str, int]:
    return {
        "maxActiveJobs": _env_int("WORKFLOW_MAX_ACTIVE_JOBS", 4),
        "backpressureWaitMs": _env_int("BACKPRESSURE_WAIT_MS", 250),
    }
