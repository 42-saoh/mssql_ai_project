from __future__ import annotations

import shutil

import pytest

from tests.e2e.web_http_adapter_smoke import run_smoke


def test_web_http_adapter_smoke_against_local_api() -> None:
    if shutil.which("pnpm") is None or shutil.which("node") is None:
        pytest.skip(
            "P18B web HTTP adapter smoke requires pnpm and node; "
            "run python3 tests/e2e/web_http_adapter_smoke.py in the web-capable environment."
        )

    run_smoke()
