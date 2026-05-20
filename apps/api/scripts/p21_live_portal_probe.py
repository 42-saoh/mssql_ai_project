#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from api_app.dependencies import reset_application_state  # noqa: E402
from api_app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

LIVE_GATE_ENV = "P21_LIVE_PORTAL_GATE"
REQUIRED_ENV = (
    "P21_LIVE_PORTAL_GATE",
    "PLATFORM_DB_HOST",
    "PLATFORM_DB_PORT",
    "PLATFORM_DB_USER",
    "PLATFORM_DB_PASSWORD",
    "PLATFORM_DB_NAME",
    "MSSQL_ENABLE_LIVE_METADATA",
    "MSSQL_METADATA_HOST",
    "MSSQL_METADATA_PORT",
    "MSSQL_METADATA_USER",
    "MSSQL_METADATA_PASSWORD",
    "MSSQL_METADATA_PROFILE_FILE",
)
REDACTION = {
    "tokens": "not_returned",
    "rawJwtClaims": "not_returned",
    "plfRows": "not_returned",
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
}


def run_probe(*, load_dotenv: bool = True) -> dict[str, Any]:
    if load_dotenv:
        load_root_dotenv()

    if not _flag_enabled(LIVE_GATE_ENV):
        return _result(
            status="skipped",
            blocker_code=None,
            summary=(
                "P21_LIVE_PORTAL_GATE is not enabled; default eval did not access PLF "
                "or live PPM metadata."
            ),
            checks=[],
        )

    missing = _missing_required_env()
    if missing:
        return _result(
            status="failed",
            blocker_code="P21_LIVE_PORTAL_REQUIRED_ENV_MISSING",
            summary="P21 live portal gate is enabled but required env names are missing.",
            checks=[
                _check(
                    "required_env",
                    "fail",
                    blocker_code="P21_LIVE_PORTAL_REQUIRED_ENV_MISSING",
                    summary="Missing env name(s): " + ", ".join(missing),
                )
            ],
        )

    reset_application_state()
    client = TestClient(app)
    try:
        metadata_result = _search_ppm_metadata(client)
        request_result = _submit_workflow(client, metadata_result)
        validation_result = _validate_artifact(client, request_result["artifactId"])
    except ProbeFailure as exc:
        return _result(
            status="failed",
            blocker_code=exc.blocker_code,
            summary=exc.summary,
            checks=exc.checks,
        )

    return _result(
        status="passed",
        blocker_code=None,
        summary=(
            "P21 live portal gate passed with PLF workflow access, live PPM metadata "
            "design-chat search, and explicit validation."
        ),
        checks=[
            _check("ppm_metadata_search", "pass", summary=metadata_result["summary"]),
            _check("workflow_submit", "pass", summary=request_result["summary"]),
            _check("explicit_validation", "pass", summary=validation_result["summary"]),
        ],
    )


def _search_ppm_metadata(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/metadata/design-runs",
        json={
            "dbProfileId": "ppm",
            "message": f"search {os.getenv('P21_METADATA_SEARCH_QUERY', 'proc')}",
            "searchInputs": {
                "query": os.getenv("P21_METADATA_SEARCH_QUERY", "proc"),
                "objectTypes": ["PROCEDURE"],
                "limit": 1,
                "includeTableSchema": False,
            },
            "options": {"useLlmAnalysis": False, "intentMode": "SEARCH_ONLY"},
        },
    )
    if response.status_code != 202:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker="P21_LIVE_PPM_UNAVAILABLE",
            check_name="ppm_metadata_search",
        )
    submitted = response.json()
    poll_response = client.get(f"/api/v1/metadata/design-runs/{submitted.get('runId')}")
    if poll_response.status_code != 200:
        raise ProbeFailure.from_response(
            poll_response,
            fallback_blocker="P21_LIVE_PPM_UNAVAILABLE",
            check_name="ppm_metadata_search",
        )
    payload = poll_response.json()
    search_result = (payload.get("result") or {}).get("searchResult") or {}
    results = search_result.get("results") or []
    if not results:
        raise ProbeFailure(
            blocker_code="P21_LIVE_PPM_UNAVAILABLE",
            summary="Live PPM metadata search returned no procedure metadata candidates.",
            checks=[
                _check(
                    "ppm_metadata_search",
                    "fail",
                    blocker_code="P21_LIVE_PPM_UNAVAILABLE",
                    summary="No row data was read; no procedure execution was performed.",
                )
            ],
        )
    identity = dict(results[0].get("objectIdentity") or {})
    return {
        "target": {
            "type": "PROCEDURE",
            "schema": str(identity.get("schema") or ""),
            "name": str(identity.get("name") or ""),
        },
        "summary": "Read-only PPM metadata design search returned a procedure identity.",
    }


def _submit_workflow(client: TestClient, metadata_result: dict[str, Any]) -> dict[str, str]:
    response = client.post(
        "/api/v1/requests/sp-analysis",
        json={
            "dbProfileId": "ppm",
            "target": metadata_result["target"],
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {"includeEvidenceRefs": True},
        },
    )
    if response.status_code != 202:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker="P21_LIVE_PLF_UNAVAILABLE",
            check_name="workflow_submit",
        )
    payload = response.json()
    job_id = str(payload.get("jobId") or "")
    if payload.get("status") == "FAILED":
        job_response = client.get(f"/api/v1/jobs/{job_id}")
        job_payload = job_response.json() if job_response.status_code == 200 else {}
        blockers = job_payload.get("blockers") or []
        code = str(blockers[0].get("code") if blockers else "P21_LIVE_PLF_UNAVAILABLE")
        raise ProbeFailure(
            blocker_code=code,
            summary=str(job_payload.get("failureReason") or "P21 workflow failed."),
            checks=[
                _check(
                    "workflow_submit",
                    "fail",
                    blocker_code=code,
                    summary="Workflow job entered FAILED state.",
                )
            ],
        )
    if payload.get("status") != "VALIDATION_COMPLETE":
        raise ProbeFailure(
            blocker_code="P25_VALIDATION_COMPLETE_STATUS_MISMATCH",
            summary="Workflow did not stop at VALIDATION_COMPLETE after validation.",
            checks=[
                _check(
                    "workflow_submit",
                    "fail",
                    blocker_code="P25_VALIDATION_COMPLETE_STATUS_MISMATCH",
                    summary=f"Unexpected job status: {payload.get('status')}",
                )
            ],
        )
    artifacts = client.get(f"/api/v1/jobs/{job_id}/artifacts")
    if artifacts.status_code != 200:
        raise ProbeFailure.from_response(
            artifacts,
            fallback_blocker="P21_LIVE_PLF_UNAVAILABLE",
            check_name="artifact_listing",
        )
    items = artifacts.json().get("artifacts") or []
    if not items:
        raise ProbeFailure(
            blocker_code="P21_LIVE_PLF_UNAVAILABLE",
            summary="PLF workflow completed without a generated artifact.",
            checks=[_check("artifact_listing", "fail", blocker_code="P21_LIVE_PLF_UNAVAILABLE")],
        )
    return {
        "jobId": job_id,
        "artifactId": str(items[0].get("artifactId") or ""),
        "summary": "PLF workflow submit returned a real job and artifact id.",
    }


def _validate_artifact(client: TestClient, artifact_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/artifacts/{artifact_id}/validation")
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker="P21_LIVE_PLF_UNAVAILABLE",
            check_name="explicit_validation",
        )
    payload = response.json()
    return {
        "validationReportId": payload.get("validationReportId"),
        "summary": "Explicit validation action persisted a PLF validation report.",
    }


class ProbeFailure(RuntimeError):
    def __init__(
        self,
        *,
        blocker_code: str,
        summary: str,
        checks: list[dict[str, Any]],
    ) -> None:
        super().__init__(summary)
        self.blocker_code = blocker_code
        self.summary = summary
        self.checks = checks

    @classmethod
    def from_response(
        cls,
        response: Any,
        *,
        fallback_blocker: str,
        check_name: str,
    ) -> ProbeFailure:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        code = str(payload.get("code") or fallback_blocker)
        detail = str(payload.get("detail") or f"HTTP {response.status_code}")
        return cls(
            blocker_code=code,
            summary=detail,
            checks=[
                _check(
                    check_name,
                    "fail",
                    blocker_code=code,
                    summary=f"HTTP {response.status_code}: {detail}",
                )
            ],
        )


def _result(
    *,
    status: str,
    blocker_code: str | None,
    summary: str,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "gate": "P21_LIVE_PORTAL_GATE",
        "status": status,
        "productionReady": False,
        "blockerCode": blocker_code,
        "summary": summary,
        "checks": checks,
        "redaction": REDACTION,
    }


def _check(
    name: str,
    status: str,
    *,
    blocker_code: str | None = None,
    summary: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "blockerCode": blocker_code,
        "summary": summary,
    }


def _missing_required_env() -> list[str]:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name, "").strip()]
    if os.getenv("MSSQL_ENABLE_LIVE_METADATA", "").strip() != "1":
        missing.append("MSSQL_ENABLE_LIVE_METADATA=1")
    return sorted(dict.fromkeys(missing))


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_root_dotenv(path: Path | None = None) -> None:
    env_path = path or REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    result = run_probe(load_dotenv=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
