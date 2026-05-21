from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from ai_agent_runtime.models import stable_json_hash
from ai_agent_runtime.storage_safety import sanitize_value_for_storage

from api_app.knowledge_service import (
    ensure_knowledge_search_filter,
    present_fact_graph,
    present_fact_search_result,
    present_knowledge_asset,
)
from api_app.presenters import (
    present_agent_run,
    present_artifact_summary,
    present_validation_report,
)
from api_app.repositories import (
    KnowledgePersistenceError,
    WorkflowRepository,
    WorkRequestRecord,
    utc_now,
)
from api_app.routes.registry import active_registry_bindings

FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "sql",
        "statement",
        "command",
        "execute",
        "execution",
        "procedure_execution",
        "ddl",
        "dml",
        "rowdata",
        "row_data",
        "rows",
        "records",
        "password",
        "secret",
        "token",
        "apikey",
        "api_key",
        "connectionstring",
        "connection_string",
        "credential",
        "definition",
        "raw_definition",
        "rawsql",
        "raw_sql",
        "prompt",
        "provider_response",
        "raw_provider_response",
        "artifact_content",
        "content",
    }
)
WRITE_SQL_PATTERN = re.compile(
    r"\b(select|insert|update|delete|merge|exec|execute|create|alter|drop|truncate)\b",
    re.IGNORECASE,
)
JOB_BOUND_TOOLS = frozenset(
    {
        "platform.list_job_artifacts",
        "platform.get_latest_validation_report",
        "platform.list_job_agent_runs",
    }
)
TOOL_LIMITS = {
    "platform.search_knowledge_facts": 50,
    "platform.list_knowledge_assets": 50,
    "platform.list_job_artifacts": 20,
    "platform.list_job_agent_runs": 20,
}


@dataclass(frozen=True)
class PlatformToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool = True
    active: bool = True
    internal_only: bool = True


@dataclass(frozen=True)
class PlatformToolDecision:
    allowed: bool
    tool_name: str
    arguments: dict[str, Any]
    code: str | None = None
    message: str | None = None


class PlatformToolError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def catalog_path() -> Path:
    return repo_root() / "spec" / "agent-tools" / "platform_ai_tool_catalog.yaml"


def load_platform_tool_catalog(path: Path | None = None) -> list[PlatformToolSpec]:
    payload = yaml.safe_load((path or catalog_path()).read_text(encoding="utf-8")) or {}
    if payload.get("service") != "platformAgentTools":
        raise ValueError("Platform AI tool catalog must declare service=platformAgentTools.")
    if payload.get("readOnly") is not True:
        raise ValueError("Platform AI tool catalog must be read-only.")
    if payload.get("internalOnly") is not True:
        raise ValueError("Platform AI tool catalog must be internal-only.")

    seen: set[str] = set()
    tools: list[PlatformToolSpec] = []
    for record in payload.get("tools", []):
        name = str(record.get("name") or "").strip()
        if not name:
            raise ValueError("Each platform tool requires a non-empty name.")
        if name in seen:
            raise ValueError(f"Duplicate platform tool name: {name}")
        seen.add(name)
        input_schema = record.get("input")
        if not isinstance(input_schema, dict):
            raise ValueError(f"Platform tool {name} requires an object input schema.")
        tools.append(
            PlatformToolSpec(
                name=name,
                description=str(record.get("description") or "").strip(),
                input_schema=input_schema,
                read_only=bool(record.get("readOnly", payload.get("readOnly", True))),
                active=bool(record.get("active", True)),
                internal_only=bool(
                    record.get("internalOnly", payload.get("internalOnly", True))
                ),
            )
        )
    if not tools:
        raise ValueError("Platform AI tool catalog must declare at least one tool.")
    return tools


class PlatformToolPolicy:
    def __init__(
        self,
        *,
        tools: list[PlatformToolSpec],
        request_record: WorkRequestRecord,
        job_id: str,
    ) -> None:
        self.request_record = request_record
        self.job_id = job_id
        self.target = _target_mapping(request_record.target)
        self._tools = {
            tool.name: tool
            for tool in tools
            if tool.active and tool.read_only and tool.internal_only
        }

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    def decide(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> PlatformToolDecision:
        normalized_tool = tool_name.strip()
        if normalized_tool not in self._tools:
            return PlatformToolDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments={},
                code="PLATFORM_TOOL_NOT_ACTIVE_READ_ONLY",
                message="요청한 platform tool은 active/read-only/internal-only 조건을 만족하지 않습니다.",
            )
        normalized_arguments = _normalized_arguments(
            arguments,
            tool_name=normalized_tool,
            request_record=self.request_record,
            job_id=self.job_id,
        )
        violation = _argument_policy_violation(normalized_arguments)
        if violation is not None:
            return PlatformToolDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments=normalized_arguments,
                code=violation[0],
                message=violation[1],
            )
        scope_violation = _scope_policy_violation(
            normalized_arguments,
            request_record=self.request_record,
            job_id=self.job_id,
            target=self.target,
        )
        if scope_violation is not None:
            return PlatformToolDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments=normalized_arguments,
                code=scope_violation[0],
                message=scope_violation[1],
            )
        return PlatformToolDecision(
            allowed=True,
            tool_name=normalized_tool,
            arguments=normalized_arguments,
        )


class PlatformToolRegistry:
    def __init__(
        self,
        *,
        repository: WorkflowRepository,
        request_record: WorkRequestRecord,
        job_id: str,
    ) -> None:
        self.repository = repository
        self.request_record = request_record
        self.job_id = job_id
        self.target = _target_mapping(request_record.target)

    def invoke_payload(self, tool_name: str, request: Mapping[str, Any]) -> dict[str, Any]:
        arguments = request.get("arguments")
        if not isinstance(arguments, Mapping):
            raise PlatformToolError(
                "Platform tool invocation에는 structured arguments가 필요합니다.",
                code="PLATFORM_TOOL_INVALID_ARGUMENTS",
            )
        try:
            if tool_name == "platform.search_knowledge_facts":
                data = self._search_knowledge_facts(arguments)
            elif tool_name == "platform.list_knowledge_assets":
                data = self._list_knowledge_assets(arguments)
            elif tool_name == "platform.get_knowledge_version_graph":
                data = self._get_knowledge_version_graph(arguments)
            elif tool_name == "platform.list_job_artifacts":
                data = self._list_job_artifacts(arguments)
            elif tool_name == "platform.get_latest_validation_report":
                data = self._get_latest_validation_report(arguments)
            elif tool_name == "platform.list_job_agent_runs":
                data = self._list_job_agent_runs(arguments)
            elif tool_name == "platform.list_registry_versions":
                data = self._list_registry_versions()
            else:
                raise PlatformToolError(
                    f"Unknown platform tool: {tool_name}",
                    code="PLATFORM_TOOL_UNKNOWN",
                )
        except KnowledgePersistenceError as exc:
            raise PlatformToolError(str(exc), code=exc.code) from exc
        return _success_payload(
            tool_name=tool_name,
            data=data,
            request_record=self.request_record,
            job_id=self.job_id,
        )

    def _search_knowledge_facts(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        target = self.target
        object_ref = str(arguments.get("objectRef") or target["ref"]).strip()
        target_name = str(arguments.get("targetName") or target["name"]).strip()
        ensure_knowledge_search_filter(
            objectRef=object_ref,
            factType=_optional_str(arguments.get("factType")),
            status=_optional_str(arguments.get("status")),
            assetKind=_optional_str(arguments.get("assetKind")),
            targetName=target_name,
            lifecycleStatus=_optional_str(arguments.get("lifecycleStatus")),
        )
        records = self.repository.search_knowledge_facts(
            object_ref=object_ref,
            fact_type=_optional_str(arguments.get("factType")),
            status=_optional_str(arguments.get("status")),
            asset_kind=_optional_str(arguments.get("assetKind")),
            target_name=target_name,
            lifecycle_status=_optional_str(arguments.get("lifecycleStatus")),
            limit=_limit(arguments, "platform.search_knowledge_facts"),
        )
        return {
            "facts": [present_fact_search_result(record).to_response() for record in records],
            "resultCount": len(records),
            "scope": _scope_payload(self.request_record, self.job_id),
        }

    def _list_knowledge_assets(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        target = self.target
        records = self.repository.list_knowledge_assets(
            asset_kind=_optional_str(arguments.get("assetKind")),
            db_profile_id=self.request_record.db_profile_id,
            target_type=target["type"],
            target_schema=target["schema"],
            target_name=target["name"],
            lifecycle_status=_optional_str(arguments.get("lifecycleStatus")),
            limit=_limit(arguments, "platform.list_knowledge_assets"),
        )
        return {
            "assets": [present_knowledge_asset(record).to_response() for record in records],
            "resultCount": len(records),
            "scope": _scope_payload(self.request_record, self.job_id),
        }

    def _get_knowledge_version_graph(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        asset_id = _required_arg(arguments, "assetId")
        version_id = _required_arg(arguments, "versionId")
        asset = self.repository.get_knowledge_asset(asset_id)
        if asset is None:
            raise PlatformToolError(
                f"Unknown knowledge asset: {asset_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        target = self.target
        if (
            asset.db_profile_id != self.request_record.db_profile_id
            or asset.target_type != target["type"]
            or asset.target_schema != target["schema"]
            or asset.target_name != target["name"]
        ):
            raise PlatformToolError(
                "Knowledge asset이 현재 request scope 밖에 있습니다.",
                code="PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED",
            )
        graph = self.repository.list_knowledge_facts(asset_id, version_id)
        if graph is None:
            raise PlatformToolError(
                f"Unknown knowledge asset version: {version_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        facts, edges = graph
        return present_fact_graph(
            asset_id=asset_id,
            version_id=version_id,
            facts=facts,
            edges=edges,
        ).to_response()

    def _list_job_artifacts(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        records = self.repository.list_job_artifacts(self.job_id)
        if records is None:
            raise PlatformToolError(
                f"Unknown job: {self.job_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        limit = _limit(arguments, "platform.list_job_artifacts")
        return {
            "artifacts": [
                present_artifact_summary(record).to_response() for record in records[:limit]
            ],
            "resultCount": min(len(records), limit),
            "scope": _scope_payload(self.request_record, self.job_id),
        }

    def _get_latest_validation_report(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        artifact_id = _required_arg(arguments, "artifactId")
        artifact = self.repository.get_artifact(artifact_id)
        if artifact is None or artifact.job_id != self.job_id:
            raise PlatformToolError(
                f"Unknown current-job artifact: {artifact_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        report = self.repository.latest_validation_for(artifact_id)
        if report is None:
            raise PlatformToolError(
                f"No validation report recorded for artifact: {artifact_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        return present_validation_report(report).to_response()

    def _list_job_agent_runs(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        records = self.repository.list_agent_runs(
            self.job_id,
            limit=_limit(arguments, "platform.list_job_agent_runs"),
        )
        if records is None:
            raise PlatformToolError(
                f"Unknown job: {self.job_id}",
                code="PLATFORM_TOOL_RESOURCE_NOT_FOUND",
            )
        return {
            "agentRuns": [present_agent_run(record).to_response() for record in records],
            "resultCount": len(records),
            "scope": _scope_payload(self.request_record, self.job_id),
        }

    def _list_registry_versions(self) -> dict[str, Any]:
        versions = [binding.to_response() for binding in active_registry_bindings()]
        return {
            "versions": versions,
            "resultCount": len(versions),
            "scope": _scope_payload(self.request_record, self.job_id),
        }


def platform_tool_capabilities(tools: list[PlatformToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": _sanitize_value(tool.input_schema),
        }
        for tool in tools
        if tool.active and tool.read_only and tool.internal_only
    ]


def _normalized_arguments(
    arguments: Mapping[str, Any],
    *,
    tool_name: str,
    request_record: WorkRequestRecord,
    job_id: str,
) -> dict[str, Any]:
    normalized = _sanitize_value(dict(arguments))
    normalized.setdefault("dbProfileId", request_record.db_profile_id)
    if tool_name in JOB_BOUND_TOOLS:
        normalized.setdefault("jobId", job_id)
    return _cap_argument_values(normalized, tool_name=tool_name)


def _cap_argument_values(value: Any, *, tool_name: str) -> Any:
    if isinstance(value, dict):
        capped = {}
        for key, item in value.items():
            if str(key) == "limit":
                capped[key] = _clamped_limit(item, tool_name)
            else:
                capped[key] = _cap_argument_values(item, tool_name=tool_name)
        return capped
    if isinstance(value, list):
        return [_cap_argument_values(item, tool_name=tool_name) for item in value]
    return value


def _argument_policy_violation(value: Any, *, path: str = "arguments") -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).replace("-", "_").lower()
            nested_path = f"{path}.{key}"
            if normalized_key in FORBIDDEN_ARGUMENT_KEYS:
                    return (
                        "PLATFORM_TOOL_FORBIDDEN_ARGUMENT",
                        f"금지된 platform tool argument key를 {nested_path}에서 차단했습니다.",
                    )
            violation = _argument_policy_violation(item, path=nested_path)
            if violation is not None:
                return violation
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            violation = _argument_policy_violation(item, path=f"{path}[{index}]")
            if violation is not None:
                return violation
        return None
    if isinstance(value, str) and _looks_like_freeform_sql(value):
        return (
            "PLATFORM_TOOL_FREEFORM_SQL_BLOCKED",
            f"free-form SQL처럼 보이는 platform tool argument를 {path}에서 차단했습니다.",
        )
    return None


def _scope_policy_violation(
    arguments: Mapping[str, Any],
    *,
    request_record: WorkRequestRecord,
    job_id: str,
    target: Mapping[str, str],
) -> tuple[str, str] | None:
    requested_profile = str(arguments.get("dbProfileId") or request_record.db_profile_id)
    if requested_profile != request_record.db_profile_id:
        return (
            "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED",
            "Platform tool orchestration은 db profile 전환을 허용하지 않습니다.",
        )
    if "jobId" in arguments and str(arguments.get("jobId") or "") != job_id:
        return (
            "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED",
            "Platform tool orchestration은 job 전환을 허용하지 않습니다.",
        )
    target_checks = {
        "targetType": target["type"],
        "targetSchema": target["schema"],
        "targetName": target["name"],
        "objectRef": target["ref"],
    }
    for key, expected in target_checks.items():
        actual = arguments.get(key)
        if actual is not None and str(actual).strip() != expected:
            return (
                "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED",
                f"Platform tool orchestration은 {key}를 통한 request target 전환을 허용하지 않습니다.",
            )
    return None


def _looks_like_freeform_sql(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if WRITE_SQL_PATTERN.search(text) and (" " in text or ";" in text):
        return True
    return "--" in text or "/*" in text or "*/" in text


def _success_payload(
    *,
    tool_name: str,
    data: Mapping[str, Any],
    request_record: WorkRequestRecord,
    job_id: str,
) -> dict[str, Any]:
    collected_at = utc_now().isoformat()
    sanitized_data = _sanitize_value(
        sanitize_value_for_storage(dict(data), procedure_definition="")
    )
    evidence_id = (
        f"platform.tool.{_tool_segment(tool_name)}."
        f"{stable_json_hash(sanitized_data)[:12]}"
    )
    return {
        "ok": True,
        "toolName": tool_name,
        "collectedAt": collected_at,
        "evidenceRefs": [
            {
                "id": evidence_id,
                "source": "PLATFORM",
                "path": f"platform-tools/{tool_name}",
                "objectName": _target_mapping(request_record.target)["ref"],
                "jobId": job_id,
            }
        ],
        "data": sanitized_data,
    }


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in {
                "definition",
                "raw_definition",
                "raw_definition_text",
                "rawsql",
                "raw_sql",
                "sqltext",
                "sql_text",
                "rowdata",
                "row_data",
                "rows",
                "records",
                "password",
                "secret",
                "token",
                "apikey",
                "api_key",
                "connectionstring",
                "connection_string",
                "artifact_content",
                "raw_prompt",
                "provider_response",
                "raw_provider_response",
            }:
                continue
            sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _target_mapping(target: Mapping[str, Any]) -> dict[str, str]:
    schema = str(target.get("schema") or target.get("schemaName") or "").strip()
    name = str(target.get("name") or "").strip()
    object_type = str(target.get("type") or "").strip().upper()
    return {"schema": schema, "name": name, "type": object_type, "ref": f"{schema}.{name}"}


def _scope_payload(request_record: WorkRequestRecord, job_id: str) -> dict[str, str]:
    target = _target_mapping(request_record.target)
    return {
        "jobId": job_id,
        "dbProfileId": request_record.db_profile_id,
        "targetType": target["type"],
        "targetRef": target["ref"],
    }


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _required_arg(arguments: Mapping[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise PlatformToolError(
            f"Missing required platform tool argument: {key}",
            code="PLATFORM_TOOL_INVALID_ARGUMENTS",
        )
    return value


def _limit(arguments: Mapping[str, Any], tool_name: str) -> int:
    value = arguments.get("limit", TOOL_LIMITS.get(tool_name, 20))
    return _clamped_limit(value, tool_name)


def _clamped_limit(value: Any, tool_name: str) -> int:
    maximum = TOOL_LIMITS.get(tool_name, 20)
    if value is None or value == "":
        return maximum
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = maximum
    return min(max(requested, 1), maximum)


def _tool_segment(tool_name: str) -> str:
    return tool_name.removeprefix("platform.")
