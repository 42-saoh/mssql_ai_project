from __future__ import annotations

import json
import os

import pytest
from scripts.p21_live_portal_probe import run_probe


def test_p21_live_portal_gate() -> None:
    if os.getenv("P21_LIVE_PORTAL_GATE") != "1":
        pytest.skip("P21_LIVE_PORTAL_GATE is not enabled; no PLF/PPM live access attempted.")

    result = run_probe(load_dotenv=True)
    if result["status"] != "passed":
        pytest.fail(json.dumps(result, ensure_ascii=False, sort_keys=True))

    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["redaction"] == {
        "tokens": "not_returned",
        "rawJwtClaims": "not_returned",
        "plfRows": "not_returned",
        "ppmRows": "not_returned",
        "connectionStrings": "not_returned",
    }
