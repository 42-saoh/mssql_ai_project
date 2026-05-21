from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "spec" / "policy"


def test_java_mybatis_policy_exists_and_parses() -> None:
    path = POLICY_DIR / "project_ai_java_mybatis_generation_policy.yaml"
    assert path.exists()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert data["policyName"] == "project-ai-java-mybatis-draft-generation"
    assert data["mode"]["generation"] == "draft_only"
    assert data["mode"]["evidence_required"] is True
    assert data["mode"]["quality_caveats_enabled"] is True
    assert "review_required" not in data["mode"]
    assert "approval_required" not in data["mode"]
    assert "metadataCrud" in data["generationModes"]
    assert "spWrapper" in data["generationModes"]
    assert "spRebuild" in data["generationModes"]
    assert "evidenceReconstructed" in data["generationModes"]


def test_platform_db_rules_exist_and_parse() -> None:
    path = POLICY_DIR / "platform_db_standardization_rules_for_ai.json"
    assert path.exists()

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["document_name"] == "Platform DB Standardization Rules for AI"
    assert data["priority_order"][0] == "current_user_request"
    assert data["global_rules"]["read_only_metadata_access_only"] is True
    assert data["global_rules"]["auto_execute_ddl"] is False
    assert data["schema_generation_rules"]["do_not_invent_new_abbreviation"] is True
    assert "schema_name" in data["metadata_usage"]["response_required_fields"]
    assert "REVIEW_REQUIRED" in data["metadata_usage"]["status_values"]


def test_policy_readme_exists() -> None:
    assert (POLICY_DIR / "README.md").exists()
