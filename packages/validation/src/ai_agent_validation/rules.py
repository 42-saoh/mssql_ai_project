from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import ArtifactType

from ai_agent_validation.models import ValidationRule, ValidationSeverity

NON_ARTIFACT_SCOPES = {"artifact-workflow", "mssql-mcp", "repository-workflow"}

ARTIFACT_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "SP_ANALYSIS_DOCUMENT": (ArtifactType.SP_ANALYSIS_DOC.value,),
    "DEPENDENCY_REPORT": (ArtifactType.DEPENDENCY_REPORT.value,),
    "JAVA_MYBATIS_DRAFT": (
        ArtifactType.DTO_DRAFT.value,
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    ),
    "DTO_MODEL_DRAFT": (
        ArtifactType.DTO_DRAFT.value,
        ArtifactType.VO_DRAFT.value,
        ArtifactType.MODEL_DRAFT.value,
    ),
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_validation_rules_path() -> Path:
    return repo_root() / "spec" / "validation" / "validation_rules.yaml"


def load_validation_rules(path: str | Path | None = None) -> tuple[ValidationRule, ...]:
    rules_path = Path(path) if path is not None else default_validation_rules_path()
    payload: dict[str, Any] = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    rules = []
    for item in payload.get("rules", []):
        severity = ValidationSeverity(str(item["severity"]).upper())
        applies_to = tuple(str(target) for target in item.get("appliesTo", []))
        rules.append(
            ValidationRule(
                id=str(item["id"]),
                severity=severity,
                applies_to=applies_to,
                description=str(item.get("description", "")),
            )
        )
    return tuple(rules)


def expand_artifact_scope(artifact_type: str | ArtifactType) -> tuple[str, ...]:
    artifact_value = artifact_type.value if hasattr(artifact_type, "value") else str(
        artifact_type
    )
    if artifact_value in ARTIFACT_TYPE_ALIASES:
        return ARTIFACT_TYPE_ALIASES[artifact_value]
    return (artifact_value,)


def rules_for_artifact(
    artifact_type: str | ArtifactType,
    rules: tuple[ValidationRule, ...] | None = None,
) -> tuple[ValidationRule, ...]:
    loaded_rules = rules if rules is not None else load_validation_rules()
    scopes = set(expand_artifact_scope(artifact_type))
    return tuple(rule for rule in loaded_rules if scopes.intersection(set(rule.applies_to)))
