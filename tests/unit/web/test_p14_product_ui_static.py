from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
WEB_ROOT = ROOT / "apps" / "web"


def _web_source() -> str:
    roots = [WEB_ROOT / "app", WEB_ROOT / "components", WEB_ROOT / "lib"]
    return "\n".join(
        path.read_text(encoding="utf-8")
        for root in roots
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )


def test_p14_sample_names_come_from_live_manifest_not_web_source() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    reader_source = (WEB_ROOT / "lib" / "pilot-manifest.ts").read_text(encoding="utf-8")
    web_source = _web_source()

    assert 'selectionMode !== "live_metadata"' in reader_source
    assert "procedureSamples: []" in reader_source

    if manifest["selection_mode"] == "live_metadata":
        manifest_names = {item["name"] for item in manifest["stored_procedures"]}
        assert {
            "GetInspItemsCd",
            "PAD_GET_BAT_LIST_PRC",
            "PCS_PY_ManageInvoiceFldSchd_PRC",
        } <= manifest_names
        for name in manifest_names:
            assert name not in web_source


def test_p14_web_source_keeps_forbidden_actions_out_of_ui() -> None:
    source = _web_source().lower()
    review_page = (
        WEB_ROOT / "app" / "review" / "decision" / "page.tsx"
    ).read_text(encoding="utf-8")

    assert "/api/v1/metadata/search" in source
    assert "/api/v1/artifacts/" in source
    assert "/publish" not in source
    assert "/deploy" not in source
    assert "/execute" not in source
    assert "createApprovalDecision" in review_page
    assert "recordDecision" in review_page
    assert "approval_preview_" not in review_page
    assert "row data" in source
    assert "ddl/dml" in source
    assert "dependency_metadata_incomplete" in source
