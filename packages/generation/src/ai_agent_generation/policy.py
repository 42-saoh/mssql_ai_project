from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_generation_policy_path() -> Path:
    return repo_root() / "spec" / "policy" / "project_ai_java_mybatis_generation_policy.yaml"


def default_template_registry_path() -> Path:
    return repo_root() / "packages" / "templates" / "artifacts" / "java_mybatis_registry.yaml"


def load_generation_policy(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path is not None else default_generation_policy_path()
    return yaml.safe_load(policy_path.read_text(encoding="utf-8"))


def load_template_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path is not None else default_template_registry_path()
    return yaml.safe_load(registry_path.read_text(encoding="utf-8"))


class GenerationPolicyError(ValueError):
    """Raised when generation policy assets are not complete enough to render safely."""


@dataclass(frozen=True)
class GenerationPolicyAssets:
    policy: Mapping[str, Any]
    registry: Mapping[str, Any]
    policy_path: Path
    registry_path: Path

    @property
    def policy_version(self) -> str:
        return str(_lookup_required(self.policy, "policyVersion"))

    @property
    def registry_version(self) -> str:
        return str(_lookup_required(self.registry, "registryVersion"))

    @property
    def policy_ref(self) -> str:
        return f"policy:{self.policy_path.name}@{self.policy_version}"

    def template(self, template_id: str) -> Mapping[str, Any]:
        value = _lookup_required(self.registry, f"templates.{template_id}")
        if not isinstance(value, Mapping):
            raise GenerationPolicyError(f"Template registry entry is not a mapping: {template_id}")
        return value

    def template_version(self, template_id: str) -> str:
        return str(_lookup_required(self.template(template_id), "version"))

    def template_ref(self, template_id: str) -> str:
        return f"template:{template_id}@{self.template_version(template_id)}"

    def todo_markers(self) -> tuple[str, ...]:
        value = _lookup_required(self.policy, "todoRules.mustMarkUnknown")
        return tuple(str(item) for item in value)

    def sql_risk_markers(self, template_id: str) -> tuple[Mapping[str, Any], ...]:
        value = self.template(template_id).get("sqlRiskMarkers", ())
        return tuple(item for item in value if isinstance(item, Mapping))


_REQUIRED_POLICY_PATHS = (
    "policyVersion",
    "mode.generation",
    "mode.evidence_required",
    "mode.quality_caveats_enabled",
    "naming.packagePattern",
    "classNames.dto",
    "classNames.vo",
    "classNames.model",
    "classNames.service",
    "classNames.mapper",
    "methodPatterns.listRetrieve",
    "methodPatterns.mapperSelect",
    "messages.patterns.business",
    "applicationYml.rootNode",
    "mybatis.configPath",
    "mybatis.mapperXmlPath",
    "mybatis.namespaceRule",
    "mybatis.sqlIdRule",
    "mybatis.sqlCommentPattern",
    "fieldMapping.nameTransform.rule",
    "fieldMapping.typeMappingDefaults",
    "draftQualityChecks",
    "todoRules.mustMarkUnknown",
)

_REQUIRED_TEMPLATE_PATHS = (
    "version",
    "requestedOutputType",
    "outputRoles",
    "draftQualityPolicyRef",
)


def load_generation_assets(
    *,
    policy_path: str | Path | None = None,
    registry_path: str | Path | None = None,
    template_ids: tuple[str, ...] = (),
) -> GenerationPolicyAssets:
    resolved_policy_path = (
        Path(policy_path) if policy_path is not None else default_generation_policy_path()
    )
    resolved_registry_path = (
        Path(registry_path) if registry_path is not None else default_template_registry_path()
    )
    assets = GenerationPolicyAssets(
        policy=load_generation_policy(resolved_policy_path),
        registry=load_template_registry(resolved_registry_path),
        policy_path=resolved_policy_path,
        registry_path=resolved_registry_path,
    )
    validate_generation_assets(assets, template_ids=template_ids)
    return assets


def validate_generation_assets(
    assets: GenerationPolicyAssets,
    *,
    template_ids: tuple[str, ...],
) -> None:
    missing = [
        f"policy.{path}"
        for path in _REQUIRED_POLICY_PATHS
        if _lookup_optional(assets.policy, path) in (None, "")
    ]
    missing.extend(
        f"registry.templates.{template_id}.{path}"
        for template_id in template_ids
        for path in _REQUIRED_TEMPLATE_PATHS
        if _lookup_optional(assets.registry, f"templates.{template_id}.{path}") in (None, "")
    )
    if missing:
        missing_text = ", ".join(missing)
        raise GenerationPolicyError(
            "Java/MyBatis generation policy assets are incomplete: " f"{missing_text}"
        )


def _lookup_required(payload: Mapping[str, Any], dotted_path: str) -> Any:
    value = _lookup_optional(payload, dotted_path)
    if value in (None, ""):
        raise GenerationPolicyError(f"Missing generation policy value: {dotted_path}")
    return value


def _lookup_optional(payload: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current
