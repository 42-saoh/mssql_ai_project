from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SELECTED_OBJECT_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("stored_procedures", "PROCEDURE"),
    ("tables", "TABLE"),
    ("views", "VIEW"),
    ("functions", "FUNCTION"),
)
REQUIRED_ARTIFACT_FIELDS = {
    "artifact_id",
    "artifact_version",
    "artifact_type",
    "selected_object_refs",
    "generation_manifest_ref",
    "evidence_refs",
}
REQUIRED_VALIDATION_FIELDS = {
    "rule_id",
    "severity",
    "status",
    "releaseCritical",
    "artifact_ref",
    "evidence_refs",
}


@dataclass(frozen=True)
class LivePilotArtifactPackageSummary:
    status: str
    issues: tuple[str, ...]
    artifact_count: int
    selected_object_coverage: float
    release_critical_item_count: int
    remaining_release_decision: str

    @property
    def passed(self) -> bool:
        return self.status == "PASSED" and not self.issues


def validate_live_pilot_artifact_package(
    package: Mapping[str, Any],
    *,
    selected_manifest: Mapping[str, Any],
    generation_manifest: Mapping[str, Any],
) -> LivePilotArtifactPackageSummary:
    issues: list[str] = []

    _validate_manifest_context(package, selected_manifest, generation_manifest, issues)
    expected_refs = selected_object_refs(selected_manifest)
    package_artifacts = _items_by_id(package.get("artifacts", ()), "artifact_id")
    generation_artifacts = _items_by_id(generation_manifest.get("artifacts", ()), "artifact_id")

    _validate_artifacts(
        package_artifacts=package_artifacts,
        generation_artifacts=generation_artifacts,
        expected_refs=expected_refs,
        generation_manifest_ref=str(package.get("source_generation_manifest", "")),
        issues=issues,
    )

    covered_refs = _covered_selected_refs(package_artifacts.values())
    missing_refs = sorted(expected_refs - covered_refs)
    invented_refs = sorted(covered_refs - expected_refs)
    if missing_refs:
        issues.append(f"selected_object_refs missing from artifacts: {', '.join(missing_refs)}")
    if invented_refs:
        issues.append(
            "selected_object_refs not found in pilot manifest: "
            f"{', '.join(invented_refs)}"
        )

    release_critical_count = _validate_validation_results(
        package=package,
        known_artifact_refs={
            *package_artifacts,
            str(package.get("artifact_set", {}).get("artifact_set_id", "")),
        },
        issues=issues,
    )

    coverage = len(covered_refs & expected_refs) / len(expected_refs) if expected_refs else 0.0
    declared_status = str(package.get("validation_status", ""))
    status = "PASSED" if declared_status == "PASSED" and not issues else "FAILED"
    return LivePilotArtifactPackageSummary(
        status=status,
        issues=tuple(issues),
        artifact_count=len(package_artifacts),
        selected_object_coverage=coverage,
        release_critical_item_count=release_critical_count,
        remaining_release_decision=str(
            package.get("live_release_decision_after_p17b", {}).get("decision", "")
        ),
    )


def selected_object_refs(selected_manifest: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for collection_name, object_type in SELECTED_OBJECT_COLLECTIONS:
        for item in selected_manifest.get(collection_name, ()) or ():
            schema = str(item.get("schema", "")).strip()
            name = str(item.get("name", "")).strip()
            if schema and name:
                refs.add(f"{object_type}:{schema}.{name}")
    return refs


def _validate_manifest_context(
    package: Mapping[str, Any],
    selected_manifest: Mapping[str, Any],
    generation_manifest: Mapping[str, Any],
    issues: list[str],
) -> None:
    if package.get("source_db") != "PPM":
        issues.append("package source_db must be PPM")
    if package.get("platform_db_context") != "PLF":
        issues.append("package platform_db_context must be PLF")
    if selected_manifest.get("source_db") != "PPM":
        issues.append("selected manifest source_db must be PPM")
    if selected_manifest.get("platform_db_context") != "PLF":
        issues.append("selected manifest platform_db_context must be PLF")
    if selected_manifest.get("selection_mode") != "live_metadata":
        issues.append("selected manifest selection_mode must be live_metadata")
    if selected_manifest.get("active_blockers"):
        issues.append("selected manifest must not carry active blockers for P17B")
    if selected_manifest.get("dependency_evidence_gate", {}).get("status") != (
        "PASSED_WITH_COMPLEX_SENTINEL_RESIDUAL_REVIEW"
    ):
        issues.append("P17A dependency evidence gate is not closed")

    policy = package.get("policy_boundaries", {}) or {}
    if policy.get("metadata_only") is not True:
        issues.append("package must be metadata_only")
    for field in (
        "row_data_allowed",
        "procedure_execution_allowed",
        "ddl_dml_allowed",
        "plf_fallback_allowed",
        "publish_or_export_allowed",
    ):
        if policy.get(field) is not False:
            issues.append(f"policy boundary {field} must be false")

    if "DEPENDENCY_METADATA_INCOMPLETE" in set(package.get("active_blockers_after_p17b", ())):
        issues.append("P17B package must not keep DEPENDENCY_METADATA_INCOMPLETE active")
    if "DRAFT_QUALITY_EVIDENCE_MISSING" not in set(
        package.get("active_blockers_after_p17b", ())
    ):
        issues.append("P17B package must keep draft-quality evidence blocker active")
    if package.get("live_release_decision_after_p17b", {}).get("decision") != "NO_GO":
        issues.append("P17B package must keep the live release decision NO_GO")
    if package.get("source_generation_manifest") != generation_manifest.get("manifest_ref"):
        issues.append("package source_generation_manifest does not match manifest_ref")


def _validate_artifacts(
    *,
    package_artifacts: Mapping[str, Mapping[str, Any]],
    generation_artifacts: Mapping[str, Mapping[str, Any]],
    expected_refs: set[str],
    generation_manifest_ref: str,
    issues: list[str],
) -> None:
    if not package_artifacts:
        issues.append("package must contain artifact records")
    if set(package_artifacts) != set(generation_artifacts):
        issues.append("package artifacts must match generation manifest artifacts")

    for artifact_id, artifact in package_artifacts.items():
        missing_fields = sorted(REQUIRED_ARTIFACT_FIELDS - set(artifact))
        if missing_fields:
            issues.append(f"{artifact_id} missing fields: {', '.join(missing_fields)}")
            continue
        if artifact.get("artifact_status") != "DRAFT":
            issues.append(f"{artifact_id} must remain DRAFT")
        if artifact.get("draft_only") is not True:
            issues.append(f"{artifact_id} must be draft_only")
        if artifact.get("metadata_only") is not True:
            issues.append(f"{artifact_id} must be metadata_only")
        if not artifact.get("evidence_refs"):
            issues.append(f"{artifact_id} must include evidence refs")
        if not artifact.get("selected_object_refs"):
            issues.append(f"{artifact_id} must bind selected object refs")
        artifact_manifest_ref = str(artifact.get("generation_manifest_ref", ""))
        if generation_manifest_ref and not artifact_manifest_ref.startswith(
            generation_manifest_ref
        ):
            issues.append(f"{artifact_id} generation_manifest_ref is not package-bound")

        artifact_refs = set(str(ref) for ref in artifact.get("selected_object_refs", ()) or ())
        invented_refs = sorted(artifact_refs - expected_refs)
        if invented_refs:
            issues.append(
                f"{artifact_id} contains invented selected refs: {', '.join(invented_refs)}"
            )

        manifest_artifact = generation_artifacts.get(artifact_id, {})
        for field in ("artifact_version", "artifact_type", "selected_object_refs"):
            if artifact.get(field) != manifest_artifact.get(field):
                issues.append(f"{artifact_id} field drift from generation manifest: {field}")


def _validate_validation_results(
    *,
    package: Mapping[str, Any],
    known_artifact_refs: set[str],
    issues: list[str],
) -> int:
    validation_results = package.get("validation_results", ()) or ()
    if not validation_results:
        issues.append("package must contain validation_results")
        return 0

    release_critical_count = 0
    for index, item in enumerate(validation_results):
        label = str(item.get("rule_id", f"validation_results[{index}]"))
        missing_fields = sorted(REQUIRED_VALIDATION_FIELDS - set(item))
        if missing_fields:
            issues.append(f"{label} missing fields: {', '.join(missing_fields)}")
            continue
        if item.get("releaseCritical") is True:
            release_critical_count += 1
            if item.get("status") != "PASSED":
                issues.append(f"{label} is release-critical but not PASSED")
        if item.get("artifact_ref") not in known_artifact_refs:
            issues.append(f"{label} artifact_ref is not known: {item.get('artifact_ref')}")
        if not item.get("evidence_refs"):
            issues.append(f"{label} must include evidence refs")

    if release_critical_count == 0:
        issues.append("package must include release-critical validation items")
    return release_critical_count


def _items_by_id(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items or ():
        if isinstance(item, Mapping):
            item_id = str(item.get(key, "")).strip()
            if item_id:
                result[item_id] = item
    return result


def _covered_selected_refs(artifacts: Sequence[Mapping[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for artifact in artifacts:
        refs.update(str(ref) for ref in artifact.get("selected_object_refs", ()) or ())
    return refs
