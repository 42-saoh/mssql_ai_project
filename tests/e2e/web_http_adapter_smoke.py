#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
for rel in [
    ROOT,
    ROOT / "apps" / "api",
    ROOT / "services" / "mssql-mcp",
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "analysis" / "src",
    ROOT / "packages" / "generation" / "src",
    ROOT / "packages" / "validation" / "src",
]:
    sys.path.insert(0, str(rel))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, URLError) as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Local API did not become healthy at {base_url}") from last_error


def _configure_fixture_backed_app():
    from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
    from api_app.main import app
    from api_app.memory_repository import MemoryWorkflowRepository
    from api_app.workflow import WorkflowService

    os.environ["MSSQL_ENABLE_LIVE_METADATA"] = "0"
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    return app, reset_application_state


def run_smoke() -> subprocess.CompletedProcess[str]:
    pnpm = os.environ.get("PNPM", "pnpm")
    if shutil.which(pnpm) is None:
        raise RuntimeError(f"Required command not found: {pnpm}")
    if shutil.which("node") is None:
        raise RuntimeError("Required command not found: node")

    import uvicorn

    app, reset_application_state = _configure_fixture_backed_app()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="p18b-web-http-smoke-api", daemon=True)
    thread.start()

    try:
        _wait_for_health(base_url)
        env = os.environ.copy()
        env["PORTAL_API_MODE"] = "http"
        env["PORTAL_API_BASE_URL"] = base_url
        return subprocess.run(
            [
                pnpm,
                "--dir",
                "apps/web",
                "run",
                "smoke:http-adapter",
                "--",
                base_url,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            check=True,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.clear()
        reset_application_state()


def main() -> int:
    run_smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
