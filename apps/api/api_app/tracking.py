from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

CORRELATION_ID_HEADER = "X-Correlation-ID"
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
TRACKING_STATE_ATTR = "tracking_context"


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for a different request body."""


@dataclass(frozen=True)
class RequestTrackingContext:
    correlation_id: str
    idempotency_key: str | None = None
    request_hash: str | None = None

    def with_request_hash(self, request_hash: str) -> RequestTrackingContext:
        return replace(self, request_hash=request_hash)

    def audit_payload(self) -> dict[str, str]:
        payload = {"correlationId": self.correlation_id}
        if self.idempotency_key:
            payload["idempotencyKey"] = self.idempotency_key
        if self.request_hash:
            payload["requestHash"] = self.request_hash
        return payload


def new_correlation_id() -> str:
    return f"corr_{uuid4().hex[:16]}"


def clean_header_value(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def tracking_context_from_headers(headers: Any) -> RequestTrackingContext:
    return RequestTrackingContext(
        correlation_id=clean_header_value(
            headers.get(CORRELATION_ID_HEADER),
            max_length=128,
        )
        or new_correlation_id(),
        idempotency_key=clean_header_value(
            headers.get(IDEMPOTENCY_KEY_HEADER),
            max_length=200,
        ),
    )


def tracking_context_from_request(request: Any) -> RequestTrackingContext:
    context = getattr(request.state, TRACKING_STATE_ATTR, None)
    if isinstance(context, RequestTrackingContext):
        return context
    context = tracking_context_from_headers(request.headers)
    setattr(request.state, TRACKING_STATE_ATTR, context)
    return context


def set_tracking_context_on_request(request: Any, context: RequestTrackingContext) -> None:
    setattr(request.state, TRACKING_STATE_ATTR, context)


def request_payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
