from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_runtime import (
    AiGenerationFrameworkAdapterRequest,
    ModelGateway,
    summarize_framework_trace,
    validate_framework_tool_context,
)
from ai_agent_runtime.models import (
    AgentRunStatus,
    ModelInvocationRecord,
    stable_json_hash,
)


@dataclass(frozen=True)
class BaselineResponsesFrameworkAdapter:
    """Test-only P43 historical adapter around the retained Responses/httpx gateway."""

    model_gateway: ModelGateway
    adapter_id: str = "baseline_internal_responses_gateway"
    candidate_framework: str = "baseline_internal_responses_gateway"

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="file_inventory")

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="file_content")

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="repair")

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return summarize_framework_trace(
            adapter_id=self.adapter_id,
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=stage,
            status=status,
            events=events,
        )

    def _invoke_gateway(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
    ) -> ModelInvocationRecord:
        invocation = self.model_gateway.draft_ai_java_mybatis_pack(
            prompt=request.prompt,
            profile=request.profile,
        )
        component = self.summarize_trace(
            request=request,
            stage=stage,
            status=invocation.status.value,
            events=(
                {
                    "eventType": "baseline_gateway_call",
                    "outputHash": invocation.output_hash,
                    "fileCount": len(invocation.structured_output.get("files", []))
                    if isinstance(invocation.structured_output, Mapping)
                    else 0,
                },
            ),
        )
        return dataclass_replace(
            invocation,
            component_invocations=(*invocation.component_invocations, component),
        )


@dataclass(frozen=True)
class FakeAiGenerationFrameworkAdapter:
    """Test-only fake framework adapter for fixture replay and orchestrator tests."""

    output: Mapping[str, Any] | None = None
    stage_outputs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    candidate_framework: str = "openai_agents_sdk_fake"
    adapter_id: str | None = None
    trace_events: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.adapter_id is None:
            object.__setattr__(self, "adapter_id", self.candidate_framework)

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="file_inventory")

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="file_content")

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="repair")

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return summarize_framework_trace(
            adapter_id=str(self.adapter_id),
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=stage,
            status=status,
            events=events,
        )

    def _build_invocation(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
    ) -> ModelInvocationRecord:
        structured_output = dict(
            self.stage_outputs.get(stage)
            or self.output
            or {
                "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
                "contractTarget": "AiJavaMyBatisDraftPack",
                "targetRef": request.target_ref,
                "sourcePolicy": "sanitized_facts_only",
                "productionReady": False,
                "files": [],
                "evidenceRefs": list(request.allowed_evidence_refs),
                "reviewMarkers": list(
                    request.quality_gates.get("requiredReviewMarkers", [])
                ),
                "qualityGates": dict(request.quality_gates),
                "assumptions": [],
            }
        )
        component = self.summarize_trace(
            request=request,
            stage=stage,
            status=AgentRunStatus.SUCCEEDED.value,
            events=(
                *self.trace_events,
                {
                    "eventType": "fake_framework_adapter_call",
                    "candidateFramework": self.candidate_framework,
                    "stage": stage,
                    "outputHash": stable_json_hash(structured_output),
                    "fileCount": len(structured_output.get("files", []))
                    if isinstance(structured_output.get("files"), Sequence)
                    else 0,
                },
            ),
        )
        return ModelInvocationRecord(
            provider=f"fake-framework-adapter:{self.candidate_framework}",
            model=request.profile.model,
            model_profile_id=request.profile.profile_id,
            model_registry_ref=request.profile.registry_ref,
            reasoning_effort=request.profile.reasoning_effort,
            prompt_version=request.prompt.prompt_version,
            output_schema_version=request.prompt.output_schema_version,
            input_hash=request.prompt.input_hash,
            prompt_hash=request.prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id=None,
            component_invocations=(component,),
        )
