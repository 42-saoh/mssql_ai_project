from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".agents" / "skills"
AGENTS = ROOT / "AGENTS.md"
SKILLS_DOC = ROOT / "SKILLS.md"
P42_TASK = ROOT / "tasks" / "0042-ai-draft-pack-renewal.md"

P42_SKILLS = {
    "ai-draft-pack-authoring": {
        "triggers": [
            "AiJavaMyBatisDraftPack.v0.1",
            "AI Draft Pack",
            "file inventory",
            "repair",
        ],
    },
    "java-mybatis-draft-validator": {
        "triggers": [
            "Java/MyBatis",
            "DTO",
            "Service",
            "MapperXML",
            "ManageBondDTO",
        ],
    },
    "sp-business-logic-migration-eval": {
        "triggers": [
            "MIGRATION_GUIDE.md",
            "CRUDFlag",
            "BondKindCode",
            "PCO_GU_ManageBond_PRC",
        ],
    },
}

REQUIRED_POLICY_MARKERS = (
    "raw SP",
    "row data",
    "procedure execution",
    "REVIEW_REQUIRED",
)


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", 2)
    return yaml.safe_load(frontmatter)


def test_p42_repo_skill_directories_and_frontmatter_exist() -> None:
    for skill_name in P42_SKILLS:
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"

        assert skill_file.exists()
        metadata = _frontmatter(skill_file)
        assert metadata["name"] == skill_name
        assert isinstance(metadata["description"], str)
        assert metadata["description"].strip()


def test_p42_repo_skill_descriptions_include_trigger_terms() -> None:
    for skill_name, expectation in P42_SKILLS.items():
        metadata = _frontmatter(SKILLS_DIR / skill_name / "SKILL.md")
        description = metadata["description"]

        for trigger in expectation["triggers"]:
            assert trigger in description


def test_p42_repo_skills_include_policy_guardrails() -> None:
    for skill_name in P42_SKILLS:
        text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")

        for marker in REQUIRED_POLICY_MARKERS:
            assert marker in text


def test_p42_repo_skills_are_registered_in_docs() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    skills_doc = SKILLS_DOC.read_text(encoding="utf-8")
    task = P42_TASK.read_text(encoding="utf-8")

    for skill_name in P42_SKILLS:
        assert skill_name in agents
        assert skill_name in skills_doc
        assert skill_name in task
