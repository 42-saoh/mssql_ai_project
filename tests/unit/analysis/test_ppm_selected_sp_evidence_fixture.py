from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_EVIDENCE = ROOT / "fixtures" / "analysis" / "ppm_selected_sp_evidence_v1.yaml"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"


def test_ppm_selected_sp_evidence_reflects_p17a_dependency_closure() -> None:
    evidence = _yaml(ANALYSIS_EVIDENCE)
    manifest = _yaml(PILOT_MANIFEST)

    assert evidence["selectionMode"] == "live_metadata"
    assert evidence["sourceProfile"] == "ppm"
    assert evidence["sourceDatabase"] == "PPM"
    assert evidence["platformDbContext"] == "PLF"
    assert evidence["metadataOnly"] is True
    assert evidence["activeBlockers"] == []
    assert "DEPENDENCY_METADATA_INCOMPLETE" in evidence["closedBlockers"]
    assert evidence["dependencyEvidenceGate"]["status"] == manifest["dependency_evidence_gate"][
        "status"
    ]
    assert evidence["dependencyEvidenceGate"]["passRatio"] > 0.5

    manifest_procedures = {
        f"{item['schema']}.{item['name']}" for item in manifest["stored_procedures"]
    }
    evidence_procedures = {
        f"{item['schema']}.{item['name']}" for item in evidence["storedProcedures"]
    }
    assert evidence_procedures == manifest_procedures
    assert all(item["reviewRequired"] is False for item in evidence["storedProcedures"])

    sentinel = next(
        item
        for item in evidence["storedProcedures"]
        if item["name"] == "PCS_PY_ManageInvoiceFldSchd_PRC"
    )
    assert sentinel["dependencyGate"]["status"] == "COMPLEX_SENTINEL_RESIDUAL_REVIEW_ALLOWED"
    assert sentinel["dependencyGate"]["reviewRequiredCount"] == 2
    assert sentinel["reviewRequired"] is False


def test_ppm_selected_sp_evidence_keeps_forbidden_payloads_out() -> None:
    evidence = _yaml(ANALYSIS_EVIDENCE)

    assert {
        "sql_definition_text",
        "procedure_execution",
        "table_rows",
        "committed_secret",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
    } <= set(evidence["forbiddenEvidence"])
    assert _forbidden_payload_paths(evidence) == []


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _forbidden_payload_paths(payload: Any, path: str = "$") -> list[str]:
    forbidden_keys = {
        "definitiontext",
        "sqldefinitiontext",
        "rawdefinitiontext",
        "rowdata",
        "samplerows",
    }
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            nested_path = f"{path}.{key}"
            if str(key).replace("_", "").lower() in forbidden_keys:
                paths.append(nested_path)
            paths.extend(_forbidden_payload_paths(value, nested_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            paths.extend(_forbidden_payload_paths(item, f"{path}[{index}]"))
    return paths
