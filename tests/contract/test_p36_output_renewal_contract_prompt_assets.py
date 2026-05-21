from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p36_output_renewal_contract.yaml"
TASK = ROOT / "tasks" / "0036-output-renewal.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"
RETIRED_PUBLIC_OUTPUT_TOKENS = (
    "DTO_MODEL_DRAFT",
    "VO_DRAFT",
    "MODEL_DRAFT",
    "DDL_DRAFT",
)
ACTIVE_PUBLIC_SURFACE_PATHS = (
    ROOT / "apps" / "api",
    ROOT / "apps" / "web",
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "generation" / "src",
    ROOT / "packages" / "validation" / "src",
    ROOT / "spec" / "openapi",
    ROOT / "spec" / "validation",
)
ACTIVE_PUBLIC_SURFACE_SUFFIXES = {".json", ".md", ".py", ".ts", ".tsx", ".yaml", ".yml"}


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p36_contract_declares_final_and_removed_outputs() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p36_output_renewal@0.1.0"
    assert contract["phase"] == "P36"
    assert contract["production_ready"] is False
    assert contract["execution_shape"]["mode"] == "sequential_only"
    assert contract["execution_shape"]["required_order"] == [
        "P36A",
        "P36B",
        "P36C",
        "P36D",
        "P36E",
    ]
    assert contract["execution_shape"]["parallel_execution_allowed"] is False

    artifact_contract = contract["artifact_contract"]
    assert artifact_contract["final_artifact_types"] == [
        "SP_ANALYSIS_DOC",
        "DEPENDENCY_REPORT",
        "DTO_DRAFT",
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    ]
    assert artifact_contract["removed_requested_output_types"] == [
        "DTO_MODEL_DRAFT",
        "DDL_DRAFT",
    ]
    assert artifact_contract["removed_artifact_types"] == [
        "VO_DRAFT",
        "MODEL_DRAFT",
        "DDL_DRAFT",
    ]


def test_p36_contract_captures_migration_guide_flow_and_evidence_policy() -> None:
    contract = _yaml(CONTRACT)

    assert contract["sp_analysis_doc"]["required_flow"] == [
        "1. SP 개요 (Overview)",
        "2. 의존성 인벤토리 (Dependency Inventory)",
        "3. DML 영향도 매트릭스 (Data Change Impact Matrix)",
        "4. 호출 흐름 (Call Flow)",
        "5. SP 복잡도 분석 (Complexity Analysis)",
        "6. Appendix",
    ]
    assert contract["dependency_report"]["semantic_role"] == "evidence_dossier"
    assert contract["java_mybatis_draft"]["semantic_role"] == (
        "evidence_backed_business_logic_draft"
    )
    assert contract["sql_statement_evidence_policy"]["allowed_form"] == (
        "bounded_sanitized_statement_evidence"
    )
    assert contract["sql_statement_evidence_policy"]["full_sp_definition_allowed"] is False
    assert contract["forbidden_behaviors"]["row_data_query"] is True
    assert contract["forbidden_behaviors"]["procedure_execution"] is True
    assert contract["forbidden_behaviors"]["business_db_ddl_or_dml"] is True


def test_p36_task_brief_records_scope_and_acceptance() -> None:
    text = TASK.read_text(encoding="utf-8")

    for required in [
        "Task 0036: Output Renewal",
        "P36A",
        "P36B",
        "P36C",
        "P36D",
        "P36E",
        "MIGRATION_GUIDE.md",
        "production_ready: false",
        "full SP definition",
    ]:
        assert required in text


def test_p36_prompt_pack_exists_and_keeps_phase_boundaries() -> None:
    prompts = [
        "36a_output_renewal_contract_assets.md",
        "36b_output_contract_cleanup.md",
        "36c_migration_guide_evidence_renderer.md",
        "36d_java_mybatis_business_logic_renderer.md",
        "36e_output_renewal_docs_readiness.md",
    ]

    for name in prompts:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert "## Role" in text
        assert "## Task" in text
        assert "## Constraints" in text
        assert "## Acceptance" in text
        assert "production_ready: false" in text or name != "36a_output_renewal_contract_assets.md"


def test_p36_retired_outputs_do_not_reappear_in_active_public_surface() -> None:
    offenders = []
    for base_path in ACTIVE_PUBLIC_SURFACE_PATHS:
        for path in base_path.rglob("*"):
            if path.suffix not in ACTIVE_PUBLIC_SURFACE_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            for token in RETIRED_PUBLIC_OUTPUT_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {token}")

    assert offenders == []


def test_p36_manifest_wires_sequential_tracks_only() -> None:
    manifest = _yaml(MANIFEST)

    basis = set(manifest["basis"])
    assert "spec/eval/p36_output_renewal_contract.yaml" in basis

    p36_waves = [wave for wave in manifest["waves"] if wave["wave"] == "W15_P36_output_renewal"]
    assert len(p36_waves) == 1
    tracks = p36_waves[0]["tracks"]
    assert [track["id"] for track in tracks] == [
        "P36A",
        "P36B",
        "P36C",
        "P36D",
        "P36E",
    ]
    assert [track.get("depends_on", []) for track in tracks] == [
        [],
        ["P36A"],
        ["P36B"],
        ["P36C"],
        ["P36D"],
    ]

    merge_order = manifest["merge_order"]
    p36_order = ["P36A", "P36B", "P36C", "P36D", "P36E"]
    p36_start = merge_order.index("P36A")
    assert merge_order[p36_start : p36_start + len(p36_order)] == p36_order
