from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".agents" / "skills"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"
CODEX_AGENTS = ROOT / ".codex" / "agents"
AGENTS_DOC = ROOT / "AGENTS.md"
SKILLS_DOC = ROOT / "SKILLS.md"
ROLES_DOC = ROOT / "ROLES.md"

NEW_FRAMEWORK_SKILLS = {
    "framework-adapter-pilot": [
        "AiGenerationFrameworkAdapter.v0.1",
        "OpenAI Agents SDK",
        "LangGraph",
        "rollback",
        "production_ready",
    ],
    "framework-trace-policy-review": [
        "tool context",
        "trace",
        "persistence",
        "checkpointer",
        "raw prompts",
    ],
    "orchestration-migration-planning": [
        "major",
        "orchestration",
        "reversible",
        "A/B replay",
        "production_ready",
    ],
}

EXISTING_SKILL_MARKERS = {
    "context7-docs": [
        "OpenAI Agents SDK",
        "LangGraph",
        "official/vendor docs",
        "raw prompts",
        "row data",
    ],
    "contract-to-code": [
        "Adapter-First Slices",
        "internal adapter injection",
        "rollback path",
        "public API",
    ],
    "quality-gate-review": [
        "Framework Adoption Checks",
        "raw trace",
        "P42 schema",
        "ManageBond-specific runtime hardcoding",
        "missing rollback path",
    ],
    "eval-fixture-authoring": [
        "Framework Replay Fixtures",
        "baseline and candidate adapters",
        "synthetic complex-SP collapse guard",
        "benchmark fixtures only",
    ],
    "docs-sync": [
        "Decision Gate Docs",
        "verification commands",
        "quality comparison",
        "rollback path",
        "residual `REVIEW_REQUIRED`",
    ],
    "ai-draft-pack-authoring": [
        "ManageBond names",
        "benchmark comparison signals",
        "production-runtime hardcoding",
    ],
    "java-mybatis-draft-validator": [
        "benchmark fixture expectations",
        "production-runtime hardcoding",
    ],
    "sp-business-logic-migration-eval": [
        "benchmark quality target",
        "production-runtime answer key",
        "hardcoded generator branch",
    ],
}

DOC_EXPECTED_MARKERS = [
    "framework-adapter-pilot",
    "framework-trace-policy-review",
    "orchestration-migration-planning",
    "framework_engineer",
    "production_ready: false",
    "REVIEW_REQUIRED",
]

DANGEROUS_APPROVAL_MARKERS = [
    "production_ready: true",
    "source apply is approved",
    "deploy is approved",
    "procedure execution allowed",
    "row data access allowed",
    "may store raw prompt",
    "may store raw provider response",
    "may store raw SP definition",
    "raw prompt storage is allowed",
    "raw provider response storage is allowed",
    "raw SP definition storage is allowed",
]


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", 2)
    return yaml.safe_load(frontmatter)


def test_post_p43_framework_skills_exist_with_triggering_frontmatter() -> None:
    for skill_name, trigger_terms in NEW_FRAMEWORK_SKILLS.items():
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_file.exists()

        metadata = _frontmatter(skill_file)
        description = metadata["description"]
        assert metadata["name"] == skill_name
        assert isinstance(description, str)
        assert description.strip()

        for trigger in trigger_terms:
            assert trigger in description or trigger in skill_file.read_text(encoding="utf-8")


def test_existing_skills_are_hardened_for_framework_readiness() -> None:
    for skill_name, markers in EXISTING_SKILL_MARKERS.items():
        text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")

        for marker in markers:
            assert marker in text


def test_codex_framework_engineer_agent_is_registered() -> None:
    config = CODEX_CONFIG.read_text(encoding="utf-8")
    agent = (CODEX_AGENTS / "framework_engineer.toml").read_text(encoding="utf-8")

    assert "[agents.framework_engineer]" in config
    assert 'config_file = "./agents/framework_engineer.toml"' in config
    assert 'name = "framework_engineer"' in agent
    assert "AiGenerationFrameworkAdapter" in agent or "internal adapter" in agent
    assert "Responses/httpx gateway" in agent
    assert "trace" in agent
    assert "production_ready" not in agent or "production_ready false" in agent


def test_existing_codex_agents_include_post_p43_boundaries() -> None:
    expectations = {
        "architect.toml": ["adapter-first", "reversible", "production_ready false"],
        "platform_worker.toml": ["internal", "public switches", "procedure execution"],
        "template_engineer.toml": ["P42/P43", "ManageBond", "runtime hardcoding"],
        "reviewer.toml": ["trace/persistence leakage", "P42 gate bypass", "rollback"],
        "docs_curator.toml": ["verification commands", "quality comparison", "REVIEW_REQUIRED"],
    }

    for file_name, markers in expectations.items():
        text = (CODEX_AGENTS / file_name).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in text


def test_skill_and_role_docs_register_framework_readiness_assets() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (AGENTS_DOC, SKILLS_DOC, ROLES_DOC)
    )

    for marker in DOC_EXPECTED_MARKERS:
        assert marker in docs
    assert ".agents/skills" in docs
    assert "BaselineResponsesFrameworkAdapter" in docs or "Responses/httpx" in docs
    assert "ManageBond" in docs
    assert "benchmark" in docs


def test_skill_readiness_assets_do_not_authorize_forbidden_behavior() -> None:
    asset_paths = [
        AGENTS_DOC,
        SKILLS_DOC,
        ROLES_DOC,
        CODEX_CONFIG,
        *(SKILLS_DIR / name / "SKILL.md" for name in NEW_FRAMEWORK_SKILLS),
        *(SKILLS_DIR / name / "SKILL.md" for name in EXISTING_SKILL_MARKERS),
        *(CODEX_AGENTS / name for name in [
            "architect.toml",
            "platform_worker.toml",
            "template_engineer.toml",
            "framework_engineer.toml",
            "reviewer.toml",
            "docs_curator.toml",
        ]),
    ]

    for path in asset_paths:
        text = path.read_text(encoding="utf-8")
        for marker in DANGEROUS_APPROVAL_MARKERS:
            assert marker not in text


def test_repo_uses_agents_and_codex_without_new_agent_directory() -> None:
    assert (ROOT / ".agents").exists()
    assert (ROOT / ".codex").exists()
    assert not (ROOT / ".agent").exists()
