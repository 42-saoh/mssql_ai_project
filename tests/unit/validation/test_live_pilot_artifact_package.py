from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from ai_agent_validation import (
    selected_object_refs,
    validate_live_pilot_artifact_package,
)

ROOT = Path(__file__).resolve().parents[3]
P17B_FIXTURE = ROOT / "fixtures" / "eval" / "live_pilot_artifact_validation_p17_v1.yaml"
GENERATION_MANIFEST = (
    ROOT / "fixtures" / "generation" / "live_pilot_artifacts_p17_v1" / "manifest.yaml"
)
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"


def test_live_pilot_artifact_package_passes_for_p17b_fixture() -> None:
    package, manifest, generation = _payloads()

    summary = validate_live_pilot_artifact_package(
        package,
        selected_manifest=manifest,
        generation_manifest=generation,
    )

    assert summary.passed, summary.issues
    assert summary.artifact_count == 3
    assert summary.selected_object_coverage == 1.0
    assert summary.release_critical_item_count == len(package["validation_results"])
    assert summary.remaining_release_decision == "NO_GO"
    assert selected_object_refs(manifest) == _covered_refs(package)


def test_live_pilot_artifact_package_rejects_release_critical_review_required() -> None:
    package, manifest, generation = _payloads()
    package = deepcopy(package)
    package["validation_results"][0]["status"] = "REVIEW_REQUIRED"

    summary = validate_live_pilot_artifact_package(
        package,
        selected_manifest=manifest,
        generation_manifest=generation,
    )

    assert not summary.passed
    assert any("release-critical but not PASSED" in issue for issue in summary.issues)


def test_live_pilot_artifact_package_rejects_invented_selected_object_ref() -> None:
    package, manifest, generation = _payloads()
    package = deepcopy(package)
    package["artifacts"][0]["selected_object_refs"].append("TABLE:dbo.NOT_SELECTED")

    summary = validate_live_pilot_artifact_package(
        package,
        selected_manifest=manifest,
        generation_manifest=generation,
    )

    assert not summary.passed
    assert any("not found in pilot manifest" in issue for issue in summary.issues)


def test_live_pilot_artifact_package_rejects_stale_dependency_blocker() -> None:
    package, manifest, generation = _payloads()
    package = deepcopy(package)
    package["active_blockers_after_p17b"].append("DEPENDENCY_METADATA_INCOMPLETE")

    summary = validate_live_pilot_artifact_package(
        package,
        selected_manifest=manifest,
        generation_manifest=generation,
    )

    assert not summary.passed
    assert any("DEPENDENCY_METADATA_INCOMPLETE" in issue for issue in summary.issues)


def _payloads() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return _yaml(P17B_FIXTURE), _yaml(PILOT_MANIFEST), _yaml(GENERATION_MANIFEST)


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _covered_refs(package: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for artifact in package["artifacts"]:
        refs.update(artifact["selected_object_refs"])
    return refs
