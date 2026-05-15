from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "prompt:sp_semantic_analysis@0.4.1"
OUTPUT_SCHEMA_VERSION = "schema:llm_semantic_analysis@0.4.1"
TOOL_PLANNER_PROMPT_VERSION = "prompt:mssql_metadata_tool_planner@0.1.0"
TOOL_PLANNER_OUTPUT_SCHEMA_VERSION = "schema:mssql_metadata_tool_plan@0.1.0"
PLATFORM_TOOL_PLANNER_PROMPT_VERSION = "prompt:platform_tool_planner@0.1.0"
PLATFORM_TOOL_PLANNER_OUTPUT_SCHEMA_VERSION = "schema:platform_tool_plan@0.1.0"
METADATA_ANALYSIS_PROMPT_VERSION = "prompt:mssql_metadata_analysis@0.1.1"
METADATA_ANALYSIS_OUTPUT_SCHEMA_VERSION = "schema:mssql_metadata_analysis@0.1.1"
SEMANTIC_MODEL_PROFILE_ID = "openai_sp_semantic_analysis"
FAST_TEST_MODEL_PROFILE_ID = "openai_fast_test"
FAST_TEST_DEFAULT_MODEL = "gpt-5-nano"
SEMANTIC_MODEL_REGISTRY_REF = "model:openai_sp_semantic_analysis@0.1.0"
FAST_TEST_MODEL_REGISTRY_REF = f"model:openai_fast_test@{FAST_TEST_DEFAULT_MODEL}@0.1.0"


def fast_test_model_registry_ref(model: str) -> str:
    return f"model:openai_fast_test@{model}@0.1.0"


class AgentRunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class LlmEvidenceStatus(StrEnum):
    INFERRED_DESCRIPTION = "INFERRED_DESCRIPTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RiskSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKER = "BLOCKER"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LlmBusinessRule(StrictModel):
    category: str
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.INFERRED_DESCRIPTION
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class LlmModernizationPoint(StrictModel):
    code: str
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class LlmRiskFlag(StrictModel):
    code: str
    severity: RiskSeverity
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class LlmReviewMarker(StrictModel):
    code: str
    message: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class LlmConversionGuidance(StrictModel):
    code: str
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class LlmMigrationGuideInsight(StrictModel):
    section: str
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    guide_element: str | None = Field(default=None, alias="guideElement")
    target_ref: str | None = Field(default=None, alias="targetRef")
    risk_area: str | None = Field(default=None, alias="riskArea")
    what_to_extract_next: str | None = Field(default=None, alias="whatToExtractNext")


class LlmSemanticAnalysisOutput(StrictModel):
    business_rules: list[LlmBusinessRule] = Field(default_factory=list, alias="businessRules")
    modernization_points: list[LlmModernizationPoint] = Field(
        default_factory=list,
        alias="modernizationPoints",
    )
    risk_flags: list[LlmRiskFlag] = Field(default_factory=list, alias="riskFlags")
    review_markers: list[LlmReviewMarker] = Field(default_factory=list, alias="reviewMarkers")
    conversion_guidance: list[LlmConversionGuidance] = Field(
        default_factory=list,
        alias="conversionGuidance",
    )
    migration_guide_insights: list[LlmMigrationGuideInsight] = Field(
        default_factory=list,
        alias="migrationGuideInsights",
    )
    assumptions: list[str] = Field(default_factory=list)

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class AiToolRequest(StrictModel):
    tool_name: str = Field(alias="toolName")
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    expected_evidence_use: str = Field(alias="expectedEvidenceUse")


class AiToolPlanningOutput(StrictModel):
    tool_requests: list[AiToolRequest] = Field(default_factory=list, alias="toolRequests")
    assumptions: list[str] = Field(default_factory=list)
    review_markers: list[LlmReviewMarker] = Field(default_factory=list, alias="reviewMarkers")

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class MetadataAnalysisInsight(StrictModel):
    code: str
    object_ref: str = Field(alias="objectRef")
    summary: str
    status: LlmEvidenceStatus = LlmEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataAnalysisInsightGroup(StrictModel):
    category: Literal[
        "COLUMN_RISK",
        "RELATIONSHIP",
        "INDEX",
        "CONSTRAINT",
        "DOCUMENTATION_GAP",
        "DTO_READINESS",
        "DEPENDENCY",
    ]
    insights: list[MetadataAnalysisInsight] = Field(default_factory=list)


class MetadataAnalysisDtoReadiness(StrictModel):
    object_ref: str = Field(alias="objectRef")
    status: Literal["READY", "PARTIAL", "REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    field_count: int = Field(default=0, alias="fieldCount")
    review_reasons: list[str] = Field(default_factory=list, alias="reviewReasons")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataAnalysisOutput(StrictModel):
    summary: str
    object_insights: list[MetadataAnalysisInsight] = Field(
        default_factory=list,
        alias="objectInsights",
    )
    insight_groups: list[MetadataAnalysisInsightGroup] = Field(
        default_factory=list,
        alias="insightGroups",
    )
    dto_readiness: list[MetadataAnalysisDtoReadiness] = Field(
        default_factory=list,
        alias="dtoReadiness",
    )
    review_markers: list[LlmReviewMarker] = Field(default_factory=list, alias="reviewMarkers")
    assumptions: list[str] = Field(default_factory=list)

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    model: str
    registry_ref: str
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "medium"


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_version: str
    output_schema_version: str
    system_prompt: str
    user_prompt: str
    input_hash: str
    prompt_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelInvocationRecord:
    provider: str
    model: str
    model_profile_id: str
    model_registry_ref: str
    reasoning_effort: str
    prompt_version: str
    output_schema_version: str
    input_hash: str
    prompt_hash: str
    output_hash: str
    status: AgentRunStatus
    structured_output: dict[str, Any]
    token_usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int | None = None
    provider_request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    component_invocations: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_storage_dict(self) -> dict[str, Any]:
        source_context_summary = _model_source_context_summary(self.component_invocations)
        analysis_coverage = dict(source_context_summary.get("analysisCoverage") or {})
        payload = {
            "provider": self.provider,
            "model": self.model,
            "modelProfileId": self.model_profile_id,
            "modelRegistryRef": self.model_registry_ref,
            "reasoningEffort": self.reasoning_effort,
            "promptVersion": self.prompt_version,
            "outputSchemaVersion": self.output_schema_version,
            "inputHash": self.input_hash,
            "promptHash": self.prompt_hash,
            "outputHash": self.output_hash,
            "status": self.status.value,
            "tokenUsage": dict(self.token_usage),
            "latencyMs": self.latency_ms,
            "analysisCoverage": analysis_coverage,
            "sourceContextSummary": source_context_summary,
        }
        if self.component_invocations:
            payload["componentInvocations"] = [dict(item) for item in self.component_invocations]
        return payload


@dataclass(frozen=True)
class AgentRunPayload:
    agent_type: str
    status: AgentRunStatus
    target_ref: str
    structured_output: dict[str, Any]
    model_invocation: ModelInvocationRecord
    summary: str

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "agentType": self.agent_type,
            "status": self.status.value,
            "targetRef": self.target_ref,
            "summary": self.summary,
            "structuredOutput": dict(self.structured_output),
            "modelInvocation": self.model_invocation.to_storage_dict(),
        }


def stable_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model_source_context_summary(
    component_invocations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summaries = [
        dict(item.get("sourceContextSummary") or {})
        for item in component_invocations
        if isinstance(item.get("sourceContextSummary"), Mapping)
    ]
    if not summaries:
        return {
            "mode": "NONE",
            "budgetStatus": "NO_SOURCE_CONTEXT",
            "selectedSpanCount": 0,
            "skippedSpanCount": 0,
            "reviewMarkers": [],
        }
    selected_count = sum(int(item.get("selectedSpanCount") or 0) for item in summaries)
    skipped_count = sum(int(item.get("skippedSpanCount") or 0) for item in summaries)
    budget_statuses = [str(item.get("budgetStatus") or "") for item in summaries]
    budget_status = (
        "REVIEW_REQUIRED"
        if any(
            status in {"PRE_PROVIDER_SHRINK", "SHRUNK_RETRY", "FALLBACK_NO_SOURCE"}
            for status in budget_statuses
        )
        else (
            "TRUNCATED_TO_BUDGET"
            if "TRUNCATED_TO_BUDGET" in budget_statuses
            else "WITHIN_BUDGET"
        )
    )
    coverage = next(
        (
            dict(item.get("analysisCoverage") or {})
            for item in summaries
            if item.get("analysisCoverage")
        ),
        {},
    )
    markers: list[dict[str, Any]] = []
    dependency_analysis: dict[str, Any] | None = None
    for item in summaries:
        for marker in item.get("reviewMarkers", []):
            if isinstance(marker, Mapping):
                markers.append(dict(marker))
        if isinstance(item.get("dependencyAnalysis"), Mapping):
            dependency_analysis = dict(item["dependencyAnalysis"])
    result = {
        "mode": "RETRIEVED_SPANS"
        if any(item.get("mode") == "RETRIEVED_SPANS" for item in summaries)
        else "NONE",
        "budgetStatus": budget_status,
        "selectedSpanCount": selected_count,
        "skippedSpanCount": skipped_count,
        "analysisCoverage": coverage,
        "reviewMarkers": markers,
    }
    if dependency_analysis is not None:
        result["dependencyAnalysis"] = dependency_analysis
    return result


def semantic_output_schema(
    allowed_evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    ref_items: dict[str, Any] = {"type": "string"}
    allowed_refs = [str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()]
    if allowed_refs:
        ref_items["enum"] = sorted(set(allowed_refs))
    evidence_ref_array = {
        "type": "array",
        "items": ref_items,
        "minItems": 1,
    }
    evidence_status = {
        "type": "string",
        "enum": [status.value for status in LlmEvidenceStatus],
    }
    return {
        "type": "object",
        "properties": {
            "businessRules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "summary": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["category", "summary", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "modernizationPoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "summary": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["code", "summary", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "riskFlags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": [severity.value for severity in RiskSeverity],
                        },
                        "summary": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["code", "severity", "summary", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "reviewMarkers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["code", "message", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "conversionGuidance": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "summary": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["code", "summary", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "migrationGuideInsights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "summary": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": evidence_ref_array,
                        "guideElement": {"type": ["string", "null"]},
                        "targetRef": {"type": ["string", "null"]},
                        "riskArea": {"type": ["string", "null"]},
                        "whatToExtractNext": {"type": ["string", "null"]},
                    },
                    "required": ["section", "summary", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "businessRules",
            "modernizationPoints",
            "riskFlags",
            "reviewMarkers",
            "conversionGuidance",
            "migrationGuideInsights",
            "assumptions",
        ],
        "additionalProperties": False,
    }


def metadata_tool_planning_output_schema(
    tool_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    tool_name_schema: dict[str, Any] = {"type": "string"}
    allowed_tool_names = [str(name) for name in (tool_names or ()) if str(name).strip()]
    if allowed_tool_names:
        tool_name_schema["enum"] = sorted(set(allowed_tool_names))
    evidence_status = {
        "type": "string",
        "enum": [LlmEvidenceStatus.REVIEW_REQUIRED.value],
    }
    return {
        "type": "object",
        "properties": {
            "toolRequests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "toolName": tool_name_schema,
                        "arguments": {"type": "object"},
                        "reason": {"type": "string"},
                        "expectedEvidenceUse": {"type": "string"},
                    },
                    "required": [
                        "toolName",
                        "arguments",
                        "reason",
                        "expectedEvidenceUse",
                    ],
                    "additionalProperties": False,
                },
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reviewMarkers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "status": evidence_status,
                        "evidenceRefs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["code", "message", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["toolRequests", "assumptions", "reviewMarkers"],
        "additionalProperties": False,
    }


def platform_tool_planning_output_schema(
    tool_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    return metadata_tool_planning_output_schema(tool_names=tool_names)


def metadata_analysis_output_schema(
    allowed_evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    ref_items: dict[str, Any] = {"type": "string"}
    allowed_refs = [str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()]
    if allowed_refs:
        ref_items["enum"] = sorted(set(allowed_refs))
    evidence_ref_array = {
        "type": "array",
        "items": ref_items,
        "minItems": 1,
    }
    evidence_status = {
        "type": "string",
        "enum": [status.value for status in LlmEvidenceStatus],
    }
    review_status = {
        "type": "string",
        "enum": [LlmEvidenceStatus.REVIEW_REQUIRED.value],
    }
    insight_item_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "objectRef": {"type": "string"},
            "summary": {"type": "string"},
            "status": evidence_status,
            "evidenceRefs": evidence_ref_array,
        },
        "required": ["code", "objectRef", "summary", "status", "evidenceRefs"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "objectInsights": {
                "type": "array",
                "items": insight_item_schema,
            },
            "insightGroups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "COLUMN_RISK",
                                "RELATIONSHIP",
                                "INDEX",
                                "CONSTRAINT",
                                "DOCUMENTATION_GAP",
                                "DTO_READINESS",
                                "DEPENDENCY",
                            ],
                        },
                        "insights": {
                            "type": "array",
                            "items": insight_item_schema,
                        },
                    },
                    "required": ["category", "insights"],
                    "additionalProperties": False,
                },
            },
            "dtoReadiness": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "objectRef": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["READY", "PARTIAL", "REVIEW_REQUIRED"],
                        },
                        "fieldCount": {"type": "integer", "minimum": 0},
                        "reviewReasons": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": [
                        "objectRef",
                        "status",
                        "fieldCount",
                        "reviewReasons",
                        "evidenceRefs",
                    ],
                    "additionalProperties": False,
                },
            },
            "reviewMarkers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "status": review_status,
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["code", "message", "status", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "summary",
            "objectInsights",
            "insightGroups",
            "dtoReadiness",
            "reviewMarkers",
            "assumptions",
        ],
        "additionalProperties": False,
    }
