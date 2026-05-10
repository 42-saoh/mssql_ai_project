from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

ERROR_CODE_HEADER = "X-Error-Code"


def error_payload(detail: str, code: str) -> dict[str, str]:
    return {"detail": detail, "code": code}


def code_for_status(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
        status.HTTP_409_CONFLICT: "IDEMPOTENCY_CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_503_SERVICE_UNAVAILABLE: "DEPENDENCY_BLOCKED",
    }
    return mapping.get(status_code, "API_ERROR")


def api_http_exception(
    *,
    status_code: int,
    detail: str,
    code: str | None = None,
) -> HTTPException:
    error_code = code or code_for_status(status_code)
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={ERROR_CODE_HEADER: error_code},
    )


def normalized_http_error_content(exc: HTTPException) -> dict[str, str]:
    code = code_for_status(exc.status_code)
    if exc.headers and exc.headers.get(ERROR_CODE_HEADER):
        code = str(exc.headers[ERROR_CODE_HEADER])
    if isinstance(exc.detail, dict):
        detail_value: Any = exc.detail.get("detail", "Request failed.")
        code = str(exc.detail.get("code", code))
    else:
        detail_value = exc.detail
    return error_payload(str(detail_value), code)
