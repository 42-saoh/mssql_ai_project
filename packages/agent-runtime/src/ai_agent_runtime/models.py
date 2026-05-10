from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "prompt:sp_semantic_analysis@0.1.0"
OUTPUT_SCHEMA_VERSION = "schema:llm_semantic_analysis@0.1.0"
SEMANTIC_MODEL_PROFILE_ID = "openai_sp_semantic_analysis"
FAST_TEST_MODEL_PROFILE_ID = "openai_fast_test"
SEMANTIC_MODEL_REGISTRY_REF = "model:openai_sp_semantic_analysis@0.1.0"
FAST_TEST_MODEL_REGISTRY_REF = "model:openai_fast_test@gpt-5-nano@0.1.0"


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


class LlmSemanticAnalysisOutput(StrictModel):
    business_rules: list[LlmBusinessRule] = Field(default_factory=list, alias="businessRules")
    modernization_points: list[LlmModernizationPoint] = Field(
        default_factory=list,
        alias="modernizationPoints",
    )
    risk_flags: list[LlmRiskFlag] = Field(default_factory=list, alias="riskFlags")
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

    def to_storage_dict(self) -> dict[str, Any]:
        return {
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
        }


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


def semantic_output_schema() -> dict[str, Any]:
    evidence_ref_array = {
        "type": "array",
        "items": {"type": "string"},
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
            "assumptions",
        ],
        "additionalProperties": False,
    }
