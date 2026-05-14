from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import httpx

from ai_agent_runtime.models import (
    FAST_TEST_DEFAULT_MODEL,
    FAST_TEST_MODEL_PROFILE_ID,
    SEMANTIC_MODEL_PROFILE_ID,
    SEMANTIC_MODEL_REGISTRY_REF,
    AgentRunStatus,
    AiToolPlanningOutput,
    LlmSemanticAnalysisOutput,
    MetadataAnalysisOutput,
    ModelInvocationRecord,
    ModelProfile,
    RenderedPrompt,
    fast_test_model_registry_ref,
    metadata_analysis_output_schema,
    metadata_tool_planning_output_schema,
    platform_tool_planning_output_schema,
    semantic_output_schema,
    stable_json_hash,
)

REMOTE_PROVIDER_OPENAI = "openai"
REMOTE_PROVIDER_PGPT = "pgpt"
PGPT_ANALYSIS_DEFAULT_MODEL = "gpt-4o"
PGPT_FAST_TEST_DEFAULT_MODEL = "gpt-4o-mini"


class ModelGatewayError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class ModelGateway(Protocol):
    def invoke_semantic_analysis(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        ...

    def plan_metadata_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        ...

    def analyze_metadata(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        ...

    def plan_platform_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        ...


def model_profile_from_env(profile_id: str | None) -> ModelProfile:
    normalized = (profile_id or SEMANTIC_MODEL_PROFILE_ID).strip() or SEMANTIC_MODEL_PROFILE_ID
    provider = remote_provider_from_env()
    if normalized in {FAST_TEST_MODEL_PROFILE_ID, "fast-test", "test"}:
        if provider == REMOTE_PROVIDER_PGPT:
            model = os.getenv("PGPT_MODEL_FAST_TEST", PGPT_FAST_TEST_DEFAULT_MODEL).strip()
            model = model or PGPT_FAST_TEST_DEFAULT_MODEL
        else:
            model = os.getenv("OPENAI_MODEL_FAST_TEST", FAST_TEST_DEFAULT_MODEL).strip()
            model = model or FAST_TEST_DEFAULT_MODEL
        return ModelProfile(
            profile_id=FAST_TEST_MODEL_PROFILE_ID,
            model=model,
            registry_ref=fast_test_model_registry_ref(model),
            reasoning_effort=(
                "none"
                if provider == REMOTE_PROVIDER_PGPT
                else os.getenv("OPENAI_REASONING_EFFORT_FAST_TEST", "low").strip() or "low"
            ),
        )
    if provider == REMOTE_PROVIDER_PGPT:
        model = os.getenv("PGPT_MODEL_ANALYSIS", PGPT_ANALYSIS_DEFAULT_MODEL).strip()
        model = model or PGPT_ANALYSIS_DEFAULT_MODEL
    else:
        model = os.getenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5").strip() or "gpt-5.5"
    return ModelProfile(
        profile_id=SEMANTIC_MODEL_PROFILE_ID,
        model=model,
        registry_ref=SEMANTIC_MODEL_REGISTRY_REF,
        reasoning_effort=(
            "none"
            if provider == REMOTE_PROVIDER_PGPT
            else os.getenv("OPENAI_REASONING_EFFORT_ANALYSIS", "medium").strip() or "medium"
        ),
    )


def build_model_gateway_from_env() -> ModelGateway:
    if os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1":
        return OpenAIModelGateway()
    return FakeModelGateway()


def remote_provider_from_env() -> str:
    provider = os.getenv("LLM_REMOTE_PROVIDER", REMOTE_PROVIDER_OPENAI).strip().lower()
    if provider in {REMOTE_PROVIDER_PGPT, "p-gpt", "private-gpt"}:
        return REMOTE_PROVIDER_PGPT
    return REMOTE_PROVIDER_OPENAI


class FakeModelGateway:
    provider = "fake-openai-compatible"

    def __init__(
        self,
        output_by_target_ref: Mapping[str, Any] | None = None,
        tool_plan_by_target_ref: Mapping[str, Any] | None = None,
        platform_tool_plan_by_target_ref: Mapping[str, Any] | None = None,
        metadata_analysis_by_target_ref: Mapping[str, Any] | None = None,
    ) -> None:
        self._output_by_target_ref = {
            target_ref: LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
            for target_ref, output in (output_by_target_ref or {}).items()
        }
        self._tool_plan_by_target_ref = {
            target_ref: AiToolPlanningOutput.model_validate(output).to_storage_dict()
            for target_ref, output in (tool_plan_by_target_ref or {}).items()
        }
        self._platform_tool_plan_by_target_ref = {
            target_ref: AiToolPlanningOutput.model_validate(output).to_storage_dict()
            for target_ref, output in (platform_tool_plan_by_target_ref or {}).items()
        }
        self._metadata_analysis_by_target_ref = {
            target_ref: MetadataAnalysisOutput.model_validate(output).to_storage_dict()
            for target_ref, output in (metadata_analysis_by_target_ref or {}).items()
        }

    def invoke_semantic_analysis(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        output = LlmSemanticAnalysisOutput.model_validate(
            self._output_by_target_ref.get(target_ref) or _default_fake_semantic_output()
        )
        structured_output = output.to_storage_dict()
        return ModelInvocationRecord(
            provider=self.provider,
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=prompt.prompt_version,
            output_schema_version=prompt.output_schema_version,
            input_hash=prompt.input_hash,
            prompt_hash=prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id="fake-response",
        )

    def plan_metadata_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        output = AiToolPlanningOutput.model_validate(
            self._tool_plan_by_target_ref.get(target_ref)
            or {"toolRequests": [], "assumptions": [], "reviewMarkers": []}
        )
        structured_output = output.to_storage_dict()
        return ModelInvocationRecord(
            provider=self.provider,
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=prompt.prompt_version,
            output_schema_version=prompt.output_schema_version,
            input_hash=prompt.input_hash,
            prompt_hash=prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id="fake-tool-plan",
        )

    def plan_platform_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        output = AiToolPlanningOutput.model_validate(
            self._platform_tool_plan_by_target_ref.get(target_ref)
            or {"toolRequests": [], "assumptions": [], "reviewMarkers": []}
        )
        structured_output = output.to_storage_dict()
        return ModelInvocationRecord(
            provider=self.provider,
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=prompt.prompt_version,
            output_schema_version=prompt.output_schema_version,
            input_hash=prompt.input_hash,
            prompt_hash=prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id="fake-platform-tool-plan",
        )

    def analyze_metadata(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        output = MetadataAnalysisOutput.model_validate(
            self._metadata_analysis_by_target_ref.get(target_ref)
            or _default_fake_metadata_analysis_output(
                allowed_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
                target_ref=target_ref,
            )
        )
        structured_output = output.to_storage_dict()
        return ModelInvocationRecord(
            provider=self.provider,
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=prompt.prompt_version,
            output_schema_version=prompt.output_schema_version,
            input_hash=prompt.input_hash,
            prompt_hash=prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id="fake-metadata-analysis",
        )


def _default_fake_semantic_output() -> dict[str, Any]:
    return {
        "businessRules": [
            {
                "category": "LLM_SEMANTIC_SUMMARY",
                "summary": (
                    "Fake model gateway가 메타데이터와 정적 분석만 사용해 생성한 "
                    "초안 의미 요약입니다."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": ["metadata.snapshot", "static.analysis"],
            }
        ],
        "modernizationPoints": [
            {
                "code": "REVIEW_SQL_BEHAVIOR_BEFORE_CONVERSION",
                "summary": (
                    "Java/MyBatis 초안 코드로 전환하기 전에 procedure 동작을 검토해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "riskFlags": [
            {
                "code": "LLM_OUTPUT_REQUIRES_HUMAN_REVIEW",
                "severity": "WARNING",
                "summary": "LLM 추론은 확인된 메타데이터 근거로 취급하지 않습니다.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_INFERENCE_REVIEW_REQUIRED",
                "message": "LLM이 추론한 의미 정보는 validation caveat로 유지합니다.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "conversionGuidance": [
            {
                "code": "DRAFT_JAVA_MYBATIS_READINESS",
                "summary": (
                    "Java/MyBatis 초안을 적용하기 전 결정론적 메타데이터와 validation caveat를 "
                    "반드시 확인해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "migrationGuideInsights": [
            {
                "section": "migration_strategy",
                "summary": (
                    "가이드 claim은 evidence와 연결하고, 미지원 전환 claim은 REVIEW_REQUIRED로 "
                    "표시합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "assumptions": [
            "Fake gateway를 사용했으며 외부 OpenAI API 요청은 보내지 않았습니다.",
            "LLM 추론은 raw prompt나 SQL text 없이 구조화 출력으로만 저장됩니다.",
        ],
    }


def _default_fake_metadata_analysis_output(
    *,
    allowed_refs: Any,
    target_ref: str,
) -> dict[str, Any]:
    refs = [str(ref) for ref in allowed_refs if str(ref).strip()]
    evidence_refs = refs[:1] or ["metadata.analysis.no_fact"]
    return {
        "summary": "Fake model gateway가 sanitized 결정론적 MCP evidence로 생성한 초안 메타데이터 분석입니다.",
        "objectInsights": [
            {
                "code": "METADATA_EVIDENCE_SUMMARY",
                "objectRef": target_ref or "metadata.analysis",
                "summary": (
                    "추론된 구조를 사용하기 전에 읽기 전용 메타데이터 evidence를 검토해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "insightGroups": [
            {
                "category": "DTO_READINESS",
                "insights": [
                    {
                        "code": "DRAFT_DTO_READINESS_REVIEW",
                        "objectRef": target_ref or "metadata.analysis",
                        "summary": (
                            "결정론적 메타데이터 profile과 review marker를 확인하기 전까지 "
                            "DTO readiness는 draft-only로 유지합니다."
                        ),
                        "status": "REVIEW_REQUIRED",
                        "evidenceRefs": evidence_refs,
                    }
                ],
            }
        ],
        "dtoReadiness": [
            {
                "objectRef": target_ref or "metadata.analysis",
                "status": "REVIEW_REQUIRED",
                "fieldCount": 0,
                "reviewReasons": ["Fake gateway는 evidence ref 범위를 넘어 DTO shape를 확정할 수 없습니다."],
                "evidenceRefs": evidence_refs,
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_METADATA_ANALYSIS_REVIEW_REQUIRED",
                "message": "Metadata LLM 추론은 REVIEW_REQUIRED 보조 정보로 유지합니다.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "assumptions": [
            "Fake gateway를 사용했으며 외부 OpenAI API 요청은 보내지 않았습니다.",
            "안전하지 않은 source text, sample record, secret-like 값은 제외했습니다.",
        ],
    }


class OpenAIModelGateway:
    provider = REMOTE_PROVIDER_OPENAI

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        provider: str | None = None,
    ) -> None:
        self.provider = _normalized_provider(provider)
        self.timeout_seconds = timeout_seconds or _env_float("OPENAI_TIMEOUT_SECONDS", 60.0)

    def invoke_semantic_analysis(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="llm_semantic_analysis",
            schema=semantic_output_schema(
                allowed_evidence_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
            ),
            parser=LlmSemanticAnalysisOutput.model_validate_json,
            invalid_code="OPENAI_STRUCTURED_OUTPUT_INVALID",
        )

    def plan_metadata_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="metadata_tool_plan",
            schema=metadata_tool_planning_output_schema(
                tool_names=prompt.metadata.get("toolNames") or (),
            ),
            parser=AiToolPlanningOutput.model_validate_json,
            invalid_code="OPENAI_TOOL_PLAN_INVALID",
        )

    def plan_platform_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="platform_tool_plan",
            schema=platform_tool_planning_output_schema(
                tool_names=prompt.metadata.get("toolNames") or (),
            ),
            parser=AiToolPlanningOutput.model_validate_json,
            invalid_code="OPENAI_PLATFORM_TOOL_PLAN_INVALID",
        )

    def analyze_metadata(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="metadata_analysis",
            schema=metadata_analysis_output_schema(
                allowed_evidence_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
            ),
            parser=MetadataAnalysisOutput.model_validate_json,
            invalid_code="OPENAI_METADATA_ANALYSIS_INVALID",
        )

    def _invoke_structured_output(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
        schema_name: str,
        schema: dict[str, Any],
        parser,
        invalid_code: str,
    ) -> ModelInvocationRecord:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ModelGatewayError(
                "OPENAI_API_KEY is required when LLM_ENABLE_REMOTE=1.",
                code="OPENAI_API_KEY_MISSING",
            )
        if prompt.metadata.get("procedureDefinitionIncluded") and (
            os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1"
        ):
            raise ModelGatewayError(
                "LLM_ALLOW_SP_TEXT=1 is required before sending SP definition text.",
                code="LLM_SP_TEXT_NOT_ALLOWED",
            )

        if self.provider == REMOTE_PROVIDER_PGPT:
            responses_url = _pgpt_responses_url()
            payload = _pgpt_payload(prompt=prompt, profile=profile)
        else:
            responses_url = _openai_responses_url()
            payload = _openai_payload(
                prompt=prompt,
                profile=profile,
                schema_name=schema_name,
                schema=schema,
            )

        started = time.monotonic()
        try:
            response = self._post_with_retry(
                responses_url=responses_url,
                api_key=api_key,
                payload=payload,
            )
            response.raise_for_status()
            if self.provider == REMOTE_PROVIDER_PGPT:
                response_payload, output_text = _pgpt_response_payload_and_output_text(response)
            else:
                response_payload, output_text = _response_payload_and_output_text(response)
            output, normalizer_components = _parse_structured_output(
                output_text=output_text,
                parser=parser,
                schema_name=schema_name,
                allowed_tool_names=prompt.metadata.get("toolNames") or (),
                provider=self.provider,
            )
        except httpx.HTTPStatusError as exc:
            raise ModelGatewayError(
                "OpenAI Responses API returned an error.",
                code=_http_error_code(exc.response.status_code),
            ) from exc
        except httpx.TimeoutException as exc:
            raise ModelGatewayError(
                "OpenAI Responses API request timed out.",
                code="OPENAI_TIMEOUT",
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelGatewayError(
                "OpenAI Responses API request failed.",
                code="OPENAI_REQUEST_FAILED",
            ) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise ModelGatewayError(
                "OpenAI response did not match the required structured output schema.",
                code=invalid_code,
            ) from exc

        structured_output = output.to_storage_dict()
        return ModelInvocationRecord(
            provider=self.provider,
            model=profile.model,
            model_profile_id=profile.profile_id,
            model_registry_ref=profile.registry_ref,
            reasoning_effort=profile.reasoning_effort,
            prompt_version=prompt.prompt_version,
            output_schema_version=prompt.output_schema_version,
            input_hash=prompt.input_hash,
            prompt_hash=prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage=_usage(response_payload),
            latency_ms=int((time.monotonic() - started) * 1000),
            provider_request_id=str(
                response_payload.get("id") or response.headers.get("x-request-id") or ""
            )
            or None,
            component_invocations=tuple(normalizer_components),
        )

    def _post_with_retry(
        self,
        *,
        responses_url: str,
        api_key: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        last_error: httpx.HTTPError | None = None
        for attempt in range(2):
            try:
                response = httpx.post(
                    responses_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt == 0:
                    time.sleep(0.25)
                    continue
                return response
            except httpx.TimeoutException:
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise ModelGatewayError("OpenAI Responses API retry failed.", code="OPENAI_RETRY_FAILED")


def _normalized_provider(provider: str | None) -> str:
    if provider is None:
        return remote_provider_from_env()
    normalized = provider.strip().lower()
    if normalized in {REMOTE_PROVIDER_PGPT, "p-gpt", "private-gpt"}:
        return REMOTE_PROVIDER_PGPT
    return REMOTE_PROVIDER_OPENAI


def _openai_responses_url() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return f"{base_url}/responses"


def _pgpt_responses_url() -> str:
    exact_url = os.getenv("OPENAI_RESPONSES_URL", "").strip()
    if exact_url:
        return exact_url
    base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise ModelGatewayError(
            "OPENAI_BASE_URL or OPENAI_RESPONSES_URL is required when "
            "LLM_REMOTE_PROVIDER=pgpt.",
            code="PGPT_RESPONSES_URL_MISSING",
        )
    if base_url.endswith("/v1"):
        return f"{base_url}/responses"
    return f"{base_url}/v1/responses"


def _openai_payload(
    *,
    prompt: RenderedPrompt,
    profile: ModelProfile,
    schema_name: str | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response_schema = schema or semantic_output_schema(
        allowed_evidence_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
    )
    payload: dict[str, Any] = {
        "model": profile.model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": prompt.system_prompt}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": prompt.user_prompt}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name or "llm_semantic_analysis",
                "strict": True,
                "schema": response_schema,
            }
        },
    }
    if profile.reasoning_effort != "none":
        payload["reasoning"] = {"effort": profile.reasoning_effort}
    return payload


def _pgpt_payload(*, prompt: RenderedPrompt, profile: ModelProfile) -> dict[str, Any]:
    return {
        "model": profile.model,
        "instructions": prompt.system_prompt,
        "input": [{"role": "user", "content": prompt.user_prompt}],
    }


def _response_payload_and_output_text(response: httpx.Response) -> tuple[dict[str, Any], str]:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        return {}, _sse_output_text(text)
    payload = response.json()
    return payload, _response_output_text(payload)


def _pgpt_response_payload_and_output_text(response: httpx.Response) -> tuple[dict[str, Any], str]:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        return {}, _sse_output_text(text)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return {}, text
    try:
        return payload, _response_output_text(payload)
    except ValueError:
        return payload, json.dumps(payload, ensure_ascii=False)


def _response_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return str(payload["output_text"])
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content.get("text"), str):
                return str(content["text"])
            if isinstance(content.get("output_text"), str):
                return str(content["output_text"])
    raise ValueError("No output text found in response.")


def _sse_output_text(text: str) -> str:
    chunks: list[str] = []
    completed_payload: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = str(payload.get("type") or payload.get("event") or "")
        if isinstance(payload.get("delta"), str) and (
            "output_text" in event_type or event_type.endswith(".delta")
        ):
            chunks.append(str(payload["delta"]))
            continue
        if isinstance(payload.get("text"), str) and (
            "output_text" in event_type or event_type.endswith(".done")
        ):
            chunks.append(str(payload["text"]))
            continue
        if isinstance(payload.get("output_text"), str):
            chunks.append(str(payload["output_text"]))
            continue
        response_payload = payload.get("response")
        if isinstance(response_payload, dict):
            completed_payload = response_payload
    if chunks:
        return "".join(chunks)
    if completed_payload is not None:
        return _response_output_text(completed_payload)
    raise ValueError("No output text found in event-stream response.")


def _parse_structured_output(
    *,
    output_text: str,
    parser,
    schema_name: str,
    allowed_tool_names: Sequence[str] = (),
    provider: str = REMOTE_PROVIDER_OPENAI,
) -> tuple[Any, list[dict[str, Any]]]:
    adapter_components: list[dict[str, Any]] = []
    if provider == REMOTE_PROVIDER_PGPT and schema_name == "llm_semantic_analysis":
        output_text, adapter_components = _pgpt_semantic_output_text(output_text)
    try:
        return parser(output_text), adapter_components
    except (json.JSONDecodeError, ValueError) as exc:
        if schema_name in {"metadata_tool_plan", "platform_tool_plan"}:
            repaired, removed_paths = _metadata_tool_plan_without_schema_drift(
                output_text,
                allowed_tool_names=allowed_tool_names,
            )
            if not removed_paths:
                raise exc
            return (
                AiToolPlanningOutput.model_validate(repaired),
                [
                    *adapter_components,
                    {
                        "component": "structured_output_normalizer",
                        "status": "SUCCEEDED",
                        "action": f"normalized_{schema_name}",
                        "removedFieldPaths": removed_paths,
                    }
                ],
            )
        if schema_name != "llm_semantic_analysis":
            raise
        repaired, removed_paths = _semantic_output_without_extra_fields(output_text)
        if not removed_paths:
            raise exc
        return (
            LlmSemanticAnalysisOutput.model_validate(repaired),
            [
                *adapter_components,
                {
                    "component": "structured_output_normalizer",
                    "status": "SUCCEEDED",
                    "action": "removed_schema_extra_fields",
                    "removedFieldPaths": removed_paths,
                }
            ],
        )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_SEMANTIC_ROOT_KEYS = (
    "businessRules",
    "modernizationPoints",
    "riskFlags",
    "reviewMarkers",
    "conversionGuidance",
    "migrationGuideInsights",
    "assumptions",
)
_SEMANTIC_ROOT_KEY_SET = set(_SEMANTIC_ROOT_KEYS)
_SEMANTIC_ROOT_ALIASES = {
    "business_rules": "businessRules",
    "modernization_points": "modernizationPoints",
    "risk_flags": "riskFlags",
    "review_markers": "reviewMarkers",
    "conversion_guidance": "conversionGuidance",
    "migration_guide_insights": "migrationGuideInsights",
}
_SEMANTIC_WRAPPER_KEYS = (
    "structuredOutput",
    "llmSemanticAnalysis",
    "semanticAnalysis",
    "analysis",
)
_TEXT_WRAPPER_KEYS = ("output_text", "text", "content", "message", "response")


def _pgpt_semantic_output_text(output_text: str) -> tuple[str, list[dict[str, Any]]]:
    payload = _pgpt_semantic_payload_from_text(output_text, depth=0)
    if payload is None:
        raise ValueError("No P-GPT semantic JSON object found.")
    canonical = _canonical_semantic_payload(payload)
    return (
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")),
        [
            {
                "component": "pgpt_structured_output_adapter",
                "status": "SUCCEEDED",
                "action": "adapted_pgpt_semantic_output",
            }
        ],
    )


def _pgpt_semantic_payload_from_text(output_text: str, *, depth: int) -> dict[str, Any] | None:
    if depth > 6:
        return None
    candidates = [output_text.strip()]
    candidates.extend(match.group(1).strip() for match in _JSON_FENCE_RE.finditer(output_text))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        payload = _pgpt_semantic_payload_from_value(value, depth=depth + 1)
        if payload is not None:
            return payload
    return None


def _pgpt_semantic_payload_from_value(value: Any, *, depth: int) -> dict[str, Any] | None:
    if depth > 6:
        return None
    if isinstance(value, str):
        return _pgpt_semantic_payload_from_text(value, depth=depth + 1)
    if isinstance(value, list):
        for item in value:
            payload = _pgpt_semantic_payload_from_value(item, depth=depth + 1)
            if payload is not None:
                return payload
        return None
    if not isinstance(value, dict):
        return None
    if _is_semantic_payload(value):
        return value
    for key in (*_SEMANTIC_WRAPPER_KEYS, *_TEXT_WRAPPER_KEYS):
        if key not in value:
            continue
        payload = _pgpt_semantic_payload_from_value(value[key], depth=depth + 1)
        if payload is not None:
            return payload
    return None


def _is_semantic_payload(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in _SEMANTIC_ROOT_KEY_SET | set(_SEMANTIC_ROOT_ALIASES))


def _canonical_semantic_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {key: [] for key in _SEMANTIC_ROOT_KEYS}
    for key, value in payload.items():
        target_key = _SEMANTIC_ROOT_ALIASES.get(key, key)
        if target_key in _SEMANTIC_ROOT_KEY_SET:
            canonical[target_key] = value
        else:
            canonical[key] = value
    return canonical


def _semantic_output_without_extra_fields(output_text: str) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return {}, []
    if not isinstance(payload, dict):
        return {}, []

    removed_paths: list[str] = []
    root_keys = {
        "businessRules",
        "business_rules",
        "modernizationPoints",
        "modernization_points",
        "riskFlags",
        "risk_flags",
        "reviewMarkers",
        "review_markers",
        "conversionGuidance",
        "conversion_guidance",
        "migrationGuideInsights",
        "migration_guide_insights",
        "assumptions",
    }
    item_keys = {
        "businessRules": {"category", "summary", "status", "evidenceRefs", "evidence_refs"},
        "business_rules": {"category", "summary", "status", "evidenceRefs", "evidence_refs"},
        "modernizationPoints": {"code", "summary", "status", "evidenceRefs", "evidence_refs"},
        "modernization_points": {"code", "summary", "status", "evidenceRefs", "evidence_refs"},
        "riskFlags": {"code", "severity", "summary", "status", "evidenceRefs", "evidence_refs"},
        "risk_flags": {"code", "severity", "summary", "status", "evidenceRefs", "evidence_refs"},
        "reviewMarkers": {"code", "message", "status", "evidenceRefs", "evidence_refs"},
        "review_markers": {"code", "message", "status", "evidenceRefs", "evidence_refs"},
        "conversionGuidance": {"code", "summary", "status", "evidenceRefs", "evidence_refs"},
        "conversion_guidance": {"code", "summary", "status", "evidenceRefs", "evidence_refs"},
        "migrationGuideInsights": {
            "section",
            "summary",
            "status",
            "evidenceRefs",
            "evidence_refs",
            "guideElement",
            "guide_element",
            "targetRef",
            "target_ref",
            "riskArea",
            "risk_area",
            "whatToExtractNext",
            "what_to_extract_next",
        },
        "migration_guide_insights": {
            "section",
            "summary",
            "status",
            "evidenceRefs",
            "evidence_refs",
            "guideElement",
            "guide_element",
            "targetRef",
            "target_ref",
            "riskArea",
            "risk_area",
            "whatToExtractNext",
            "what_to_extract_next",
        },
    }
    required_item_keys = {
        "businessRules": {"category", "summary"},
        "business_rules": {"category", "summary"},
        "modernizationPoints": {"code", "summary"},
        "modernization_points": {"code", "summary"},
        "riskFlags": {"code", "severity", "summary"},
        "risk_flags": {"code", "severity", "summary"},
        "reviewMarkers": {"code", "message"},
        "review_markers": {"code", "message"},
        "conversionGuidance": {"code", "summary"},
        "conversion_guidance": {"code", "summary"},
        "migrationGuideInsights": {"section", "summary"},
        "migration_guide_insights": {"section", "summary"},
    }

    repaired: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in root_keys:
            removed_paths.append(f"$.{key}")
            continue
        if key == "assumptions" and isinstance(value, list):
            repaired[key] = [
                _assumption_without_provider_text(
                    item,
                    path=f"$.assumptions[{index}]",
                    removed_paths=removed_paths,
                )
                for index, item in enumerate(value)
            ]
            continue
        if key in item_keys:
            repaired[key] = _claim_items_without_schema_drift(
                _claim_value_list(
                    value,
                    path=f"$.{key}",
                    removed_paths=removed_paths,
                ),
                field_name=key,
                allowed_keys=item_keys[key],
                required_keys=required_item_keys[key],
                path=f"$.{key}",
                removed_paths=removed_paths,
            )
            continue
        repaired[key] = value
    return repaired, sorted(removed_paths)


def _metadata_tool_plan_without_schema_drift(
    output_text: str,
    *,
    allowed_tool_names: Sequence[str],
) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return {}, []
    if not isinstance(payload, dict):
        return {}, []

    removed_paths: list[str] = []
    allowed_roots = {
        "toolRequests",
        "tool_requests",
        "tools",
        "requests",
        "assumptions",
        "reviewMarkers",
        "review_markers",
    }
    repaired: dict[str, Any] = {
        "toolRequests": [],
        "assumptions": [],
        "reviewMarkers": [],
    }
    tool_request_key, tool_request_value = _first_present(
        payload,
        ("toolRequests", "tool_requests", "tools", "requests"),
    )
    if tool_request_key and tool_request_key != "toolRequests":
        removed_paths.append(f"$.{tool_request_key}")
    repaired["toolRequests"] = _tool_request_items_without_schema_drift(
        _claim_value_list(
            tool_request_value if tool_request_key else [],
            path=f"$.{tool_request_key or 'toolRequests'}",
            removed_paths=removed_paths,
        ),
        allowed_tool_names=allowed_tool_names,
        path=f"$.{tool_request_key or 'toolRequests'}",
        removed_paths=removed_paths,
    )

    assumptions = payload.get("assumptions", [])
    if isinstance(assumptions, list):
        repaired["assumptions"] = [
            _assumption_without_provider_text(
                item,
                path=f"$.assumptions[{index}]",
                removed_paths=removed_paths,
            )
            for index, item in enumerate(assumptions)
        ]
    elif assumptions:
        removed_paths.append("$.assumptions")

    marker_key, marker_value = _first_present(payload, ("reviewMarkers", "review_markers"))
    if marker_key and marker_key != "reviewMarkers":
        removed_paths.append(f"$.{marker_key}")
    repaired["reviewMarkers"] = _claim_items_without_schema_drift(
        _claim_value_list(
            marker_value if marker_key else [],
            path=f"$.{marker_key or 'reviewMarkers'}",
            removed_paths=removed_paths,
        ),
        field_name="reviewMarkers",
        allowed_keys={"code", "message", "status", "evidenceRefs", "evidence_refs"},
        required_keys={"code", "message"},
        path=f"$.{marker_key or 'reviewMarkers'}",
        removed_paths=removed_paths,
    )

    for key in payload:
        if key not in allowed_roots:
            removed_paths.append(f"$.{key}")
    return repaired, sorted(set(removed_paths))


def _first_present(payload: Mapping[str, Any], keys: Sequence[str]) -> tuple[str | None, Any]:
    for key in keys:
        if key in payload:
            return key, payload[key]
    return None, None


def _tool_request_items_without_schema_drift(
    value: list[Any],
    *,
    allowed_tool_names: Sequence[str],
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    allowed = {str(name) for name in allowed_tool_names if str(name).strip()}
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        tool_name = _first_string(
            raw_item,
            ("toolName", "tool_name", "tool", "name"),
        )
        if not tool_name or (allowed and tool_name not in allowed):
            removed_paths.append(f"{item_path}.toolName")
            continue
        arguments = _first_mapping(
            raw_item,
            ("arguments", "args", "parameters"),
        )
        reason = _first_string(raw_item, ("reason", "rationale", "why")) or (
            "Planner returned a normalized read-only metadata request."
        )
        expected = _first_string(
            raw_item,
            ("expectedEvidenceUse", "expected_evidence_use", "evidenceUse", "evidence_use"),
        ) or "Use sanitized metadata evidence for later REVIEW_REQUIRED claims."
        repaired_items.append(
            {
                "toolName": tool_name,
                "arguments": dict(arguments),
                "reason": reason,
                "expectedEvidenceUse": expected,
            }
        )
        canonical_aliases = {
            "toolName",
            "tool_name",
            "tool",
            "name",
            "arguments",
            "args",
            "parameters",
            "reason",
            "rationale",
            "why",
            "expectedEvidenceUse",
            "expected_evidence_use",
            "evidenceUse",
            "evidence_use",
        }
        for key in raw_item:
            if key not in canonical_aliases:
                removed_paths.append(f"{item_path}.{key}")
            elif key not in {"toolName", "arguments", "reason", "expectedEvidenceUse"}:
                removed_paths.append(f"{item_path}.{key}")
    return repaired_items


def _first_string(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_mapping(payload: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _assumption_without_provider_text(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> str:
    if isinstance(value, str):
        return value
    removed_paths.append(path)
    return "Provider returned a structured assumption object; text was not stored."


def _claim_items_without_schema_drift(
    value: list[Any],
    *,
    field_name: str,
    allowed_keys: set[str],
    required_keys: set[str],
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(value):
        item = _claim_item_without_schema_drift(
            raw_item,
            field_name=field_name,
            allowed_keys=allowed_keys,
            required_keys=required_keys,
            path=f"{path}[{index}]",
            removed_paths=removed_paths,
        )
        if item is not None:
            repaired_items.append(item)
    return repaired_items


def _claim_value_list(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[Any]:
    if isinstance(value, list):
        return value
    removed_paths.append(path)
    if isinstance(value, dict):
        for nested_value in value.values():
            if isinstance(nested_value, list):
                return nested_value
        return [value]
    return []


def _claim_item_without_schema_drift(
    value: Any,
    *,
    field_name: str,
    allowed_keys: set[str],
    required_keys: set[str],
    path: str,
    removed_paths: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        removed_paths.append(path)
        return None
    normalized = _normalized_claim_item(value, field_name=field_name, path=path)
    _normalize_claim_status(
        normalized,
        field_name=field_name,
        path=path,
        removed_paths=removed_paths,
    )
    _normalize_risk_severity(normalized, path=path, removed_paths=removed_paths)
    _normalize_migration_guide_optional_text_fields(
        normalized,
        field_name=field_name,
        path=path,
        removed_paths=removed_paths,
    )
    if not required_keys <= set(normalized):
        removed_paths.append(path)
        return None
    repaired: dict[str, Any] = {}
    for key, nested_value in normalized.items():
        if key not in allowed_keys:
            removed_paths.append(f"{path}.{key}")
            continue
        repaired[key] = nested_value
    return repaired


def _normalize_claim_status(
    value: dict[str, Any],
    *,
    field_name: str,
    path: str,
    removed_paths: list[str],
) -> None:
    status = value.get("status")
    if status in {"INFERRED_DESCRIPTION", "REVIEW_REQUIRED"}:
        return
    if status is not None:
        removed_paths.append(f"{path}.status")
    if field_name in {"businessRules", "business_rules"}:
        value["status"] = "INFERRED_DESCRIPTION"
    else:
        value["status"] = "REVIEW_REQUIRED"


def _normalize_risk_severity(
    value: dict[str, Any],
    *,
    path: str,
    removed_paths: list[str],
) -> None:
    severity = value.get("severity")
    if severity is None or severity in {"INFO", "WARNING", "ERROR", "BLOCKER"}:
        return
    removed_paths.append(f"{path}.severity")
    value["severity"] = "WARNING"


def _normalize_migration_guide_optional_text_fields(
    value: dict[str, Any],
    *,
    field_name: str,
    path: str,
    removed_paths: list[str],
) -> None:
    if field_name not in {"migrationGuideInsights", "migration_guide_insights"}:
        return
    for key in (
        "guideElement",
        "guide_element",
        "targetRef",
        "target_ref",
        "riskArea",
        "risk_area",
        "whatToExtractNext",
        "what_to_extract_next",
    ):
        if key not in value:
            continue
        normalized_text = _provider_optional_text(value[key])
        if normalized_text is None:
            if value[key] is not None:
                removed_paths.append(f"{path}.{key}")
                value.pop(key, None)
            continue
        if normalized_text != value[key]:
            removed_paths.append(f"{path}.{key}")
        value[key] = normalized_text


def _normalized_claim_item(
    value: dict[str, Any],
    *,
    field_name: str,
    path: str,
) -> dict[str, Any]:
    normalized = dict(value)
    summary = _provider_text_value(
        normalized,
        ("summary", "text", "description", "rule", "item", "guidance", "insight", "message"),
    )
    if field_name in {"businessRules", "business_rules"}:
        normalized.setdefault("category", _provider_code_value(normalized, path=path))
        if summary:
            normalized.setdefault("summary", summary)
    elif field_name in {"riskFlags", "risk_flags"}:
        normalized.setdefault("code", _provider_code_value(normalized, path=path))
        normalized.setdefault("severity", "WARNING")
        if summary:
            normalized.setdefault("summary", summary)
    elif field_name in {"reviewMarkers", "review_markers"}:
        normalized.setdefault("code", _provider_code_value(normalized, path=path))
        if summary:
            normalized.setdefault("message", summary)
    elif field_name in {"migrationGuideInsights", "migration_guide_insights"}:
        normalized.setdefault("section", _provider_code_value(normalized, path=path))
        if summary:
            normalized.setdefault("summary", summary)
    else:
        normalized.setdefault("code", _provider_code_value(normalized, path=path))
        if summary:
            normalized.setdefault("summary", summary)
    return normalized


def _provider_code_value(value: dict[str, Any], *, path: str) -> str:
    for key in ("code", "category", "section", "type", "name"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    normalized_path = (
        path.replace("$.", "")
        .replace("[", "_")
        .replace("]", "")
        .replace(".", "_")
        .upper()
    )
    return f"NORMALIZED_PROVIDER_{normalized_path}"


def _provider_text_value(value: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        candidate = value.get(key)
        text = _first_text(candidate)
        if text:
            return text
    return None


def _provider_optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [_first_text(item) for item in value]
        return "; ".join(part for part in parts if part) or None
    if isinstance(value, dict):
        return _first_text(value)
    return None


def _first_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _provider_text_value(
            value,
            ("summary", "text", "description", "rule", "item", "guidance", "insight", "message"),
        )
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    return None


def _usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    return {
        "inputTokens": int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
        "outputTokens": int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
        "totalTokens": int(usage.get("total_tokens") or usage.get("totalTokens") or 0),
    }


def _http_error_code(status_code: int) -> str:
    if status_code == 429:
        return "OPENAI_RATE_LIMITED"
    if status_code == 408:
        return "OPENAI_TIMEOUT"
    if 500 <= status_code <= 599:
        return "OPENAI_SERVER_ERROR"
    return f"OPENAI_HTTP_{status_code}"


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)
