from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
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
                    "Draft semantic summary generated by the fake model gateway from "
                    "metadata and static analysis only."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": ["metadata.snapshot", "static.analysis"],
            }
        ],
        "modernizationPoints": [
            {
                "code": "REVIEW_SQL_BEHAVIOR_BEFORE_CONVERSION",
                "summary": (
                    "Review procedure behavior before converting it to Java/MyBatis "
                    "draft code."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "riskFlags": [
            {
                "code": "LLM_OUTPUT_REQUIRES_HUMAN_REVIEW",
                "severity": "WARNING",
                "summary": "LLM inference is not treated as confirmed metadata evidence.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_INFERENCE_REVIEW_REQUIRED",
                "message": "LLM-inferred semantics remain validation caveats.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "conversionGuidance": [
            {
                "code": "DRAFT_JAVA_MYBATIS_READINESS",
                "summary": (
                    "Use the deterministic metadata and validation caveats before applying "
                    "any Java/MyBatis draft."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "migrationGuideInsights": [
            {
                "section": "migration_strategy",
                "summary": (
                    "Keep guide claims evidence-linked and mark unsupported conversion "
                    "claims as REVIEW_REQUIRED."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "assumptions": [
            "Fake gateway was used; no external OpenAI API request was sent.",
            "LLM inference is stored as structured output without raw prompt or SQL text.",
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
        "summary": (
            "Draft metadata analysis generated by the fake model gateway from "
            "sanitized deterministic MCP evidence."
        ),
        "objectInsights": [
            {
                "code": "METADATA_EVIDENCE_SUMMARY",
                "objectRef": target_ref or "metadata.analysis",
                "summary": (
                    "Review read-only metadata evidence before relying on inferred structure."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_METADATA_ANALYSIS_REVIEW_REQUIRED",
                "message": "Metadata LLM inference remains a review-required aid.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "assumptions": [
            "Fake gateway was used; no external OpenAI API request was sent.",
            "Unsafe source text, sample records, and secret-like values are excluded.",
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
            response_payload, output_text = _response_payload_and_output_text(response)
            output = parser(output_text)
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
