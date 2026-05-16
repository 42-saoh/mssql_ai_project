from __future__ import annotations

import json
import os

import pytest
from scripts.auth_rbac_live_probe import run_probe


def test_p20_auth_rbac_live_gate() -> None:
    if os.getenv("AUTH_RBAC_LIVE_GATE", "").strip() != "1":
        pytest.skip(
            "P20 auth/RBAC live gate requires AUTH_RBAC_LIVE_GATE=1. "
            "Default eval remains fixture-first and does not call IdP/JWKS or PLF."
        )

    result = run_probe()
    if result["status"] != "passed":
        pytest.fail(json.dumps(result, ensure_ascii=True, sort_keys=True))

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["user_token_plf_role"]["roleCategory"] in {"USER_ONLY", "PLF_ACTOR"}
    assert checks["missing_token_401_semantics"]["status"] == "pass"
    assert checks["invalid_token_401_semantics"]["status"] == "pass"
