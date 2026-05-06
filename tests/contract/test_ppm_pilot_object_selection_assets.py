from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1"


def _yaml(name: str) -> dict:
    return yaml.safe_load((PILOT_DIR / name).read_text(encoding="utf-8"))


def test_ppm_pilot_selection_assets_exist_and_parse() -> None:
    assert (PILOT_DIR / "README.md").exists()
    assert (PILOT_DIR / "selected_objects.yaml").exists()
    assert (PILOT_DIR / "candidate_inventory_template.yaml").exists()
    assert (PILOT_DIR / "dependency_evidence_closure_v1.yaml").exists()
    assert isinstance(_yaml("selected_objects.yaml"), dict)
    assert isinstance(_yaml("candidate_inventory_template.yaml"), dict)
    assert isinstance(_yaml("dependency_evidence_closure_v1.yaml"), dict)


def test_selected_objects_records_template_or_live_metadata_selection() -> None:
    payload = _yaml("selected_objects.yaml")

    assert payload["selection_version"] == "ppm_object_selection_v1"
    assert payload["source_db"] == "PPM"
    assert payload["platform_db_context"] == "PLF"
    assert payload["connection_profile_used"]["profile_id"] == "ppm"
    assert payload["connection_profile_used"]["database"] == "PPM"
    assert payload["selection_mode"] in {"template_only", "live_metadata"}

    if payload["selection_mode"] == "template_only":
        assert payload["connection_profile_used"]["live_connection_verified"] is False
        assert payload["stored_procedures"] == []
        assert payload["tables"] == []
        assert payload["views"] == []
        assert payload["functions"] == []
    else:
        assert payload["connection_profile_used"]["live_connection_verified"] is True
        assert {item["complexity"] for item in payload["stored_procedures"]} == {
            "simple",
            "medium",
            "complex",
        }
        assert len(payload["tables"]) >= 3
        assert len(payload["views"]) >= 1
        assert len(payload["functions"]) >= 1
        assert payload["active_blockers"][0]["code"] == "DEPENDENCY_METADATA_INCOMPLETE"
        for item in payload["stored_procedures"]:
            evidence = item["metadata_evidence"]
            assert evidence["source_profile"] == "ppm"
            assert evidence["source_database"] == "PPM"
            assert evidence["definition_hash"]
            assert "definition" not in item

    blockers = {item["code"] for item in payload["blocker_candidates"]}
    assert {
        "PPM_DB_NOT_FOUND",
        "PPM_DB_ACCESS_DENIED",
        "METADATA_READ_ONLY_PERMISSION_INSUFFICIENT",
        "SP_DEFINITION_ACCESS_DENIED",
        "DEPENDENCY_METADATA_INCOMPLETE",
        "PPM_PLF_ROLE_CONFLICT",
        "LIVE_METADATA_UNAVAILABLE",
        "MIN_METADATA_DISCOVERY_SURFACE_INSUFFICIENT",
    }.issubset(blockers)
    required_tools = set(payload["minimum_metadata_discovery_surface"]["required_tools"])
    assert {
        "check_database_exists",
        "list_procedures",
        "list_tables",
        "list_views",
        "list_functions",
    }.issubset(required_tools)


def test_candidate_inventory_template_is_metadata_only_and_covers_selection_rules() -> None:
    payload = _yaml("candidate_inventory_template.yaml")

    assert payload["inventory_version"] == "ppm_object_selection_v1"
    assert payload["source_db"] == "PPM"
    assert payload["platform_db_context"] == "PLF"
    assert payload["metadata_only"] is True
    assert payload["connection_profile_used"]["profile_id"] == "ppm"
    assert "user_table_row_data" in payload["metadata_sources_forbidden"]
    assert "procedure_execution" in payload["metadata_sources_forbidden"]
    assert "MIN_METADATA_DISCOVERY_SURFACE_INSUFFICIENT" in {
        item["code"] for item in payload["blocker_candidates"]
    }

    sp_rules = payload["selection_rules"]["stored_procedures"]
    assert sp_rules["minimum_recommended"] >= 3
    for bucket in ("simple", "medium", "complex"):
        assert bucket in payload["candidate_stored_procedures"]
        assert bucket in sp_rules["complexity_buckets"]

    table_rules = payload["selection_rules"]["tables"]
    assert table_rules["minimum_recommended"] >= 3
    assert "pk_fk_index_constraint" in table_rules["preferred_features"]


def test_dependency_evidence_closure_preserves_blocker_until_hard_live_confirmation() -> None:
    selected = _yaml("selected_objects.yaml")
    closure = _yaml("dependency_evidence_closure_v1.yaml")

    assert closure["track"] == "P17A"
    assert closure["source_db"] == "PPM"
    assert closure["platform_db_context"] == "PLF"
    assert closure["policy_boundaries"]["metadata_only"] is True
    assert closure["policy_boundaries"]["row_data_allowed"] is False
    assert closure["policy_boundaries"]["procedure_execution_allowed"] is False
    assert closure["policy_boundaries"]["plf_fallback_allowed"] is False
    assert closure["implemented_metadata_resolver"]["tool"] == "get_procedure_dependencies"
    assert closure["implemented_metadata_resolver"]["input_contract_changed"] is False

    selected_blockers = {item["code"] for item in selected["active_blockers"]}
    if closure["dependency_metadata"]["blocker_closed"]:
        assert "DEPENDENCY_METADATA_INCOMPLETE" not in selected_blockers
    else:
        assert closure["dependency_metadata"]["active_blocker"] == "DEPENDENCY_METADATA_INCOMPLETE"
        assert "DEPENDENCY_METADATA_INCOMPLETE" in selected_blockers

    for table in selected["tables"]:
        for related in table.get("related_procedures", []):
            assert related["resolutionStatus"] == "CONFIRMED"
            assert related["evidenceRefs"]


def test_pilot_assets_do_not_encode_row_data_or_pfl_typo() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in PILOT_DIR.iterdir() if path.is_file()
    )
    forbidden_terms = (
        "sample_rows",
        "row_sample",
        "SELECT * FROM PPM",
        "TOP N",
        "COUNT(*)",
        "PFL",
    )
    for term in forbidden_terms:
        assert term not in combined


def test_local_profile_registry_contains_ppm_and_plf_roles() -> None:
    registry = yaml.safe_load(
        (ROOT / "config" / "mssql" / "local_docker_profiles.yaml").read_text(
            encoding="utf-8"
        )
    )
    profiles = {profile["id"]: profile for profile in registry["profiles"]}

    assert profiles["plf"]["database"] == "PLF"
    assert profiles["plf"]["purpose"] == "platform"
    assert profiles["ppm"]["database"] == "PPM"
    assert profiles["ppm"]["purpose"] == "pilot-analysis-target"
    assert profiles["master"]["database"] == "master"
