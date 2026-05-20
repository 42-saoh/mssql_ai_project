from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import httpx

from ai_agent_runtime.ai_draft_pack import (
    AiDraftPackValidationError,
    ai_java_mybatis_draft_pack_output_schema,
    parse_ai_java_mybatis_draft_pack_json,
    validate_ai_java_mybatis_draft_pack_output,
)
from ai_agent_runtime.models import (
    AI_DRAFT_PACK_MODEL_PROFILE_ID,
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
    ai_draft_pack_model_registry_ref,
    fast_test_model_registry_ref,
    metadata_analysis_output_schema,
    metadata_tool_planning_output_schema,
    platform_tool_planning_output_schema,
    semantic_output_schema,
    stable_json_hash,
)
from ai_agent_runtime.operation_model import (
    OperationModelValidationError,
    parse_sp_operation_model_json,
    sp_operation_model_output_schema,
    validate_sp_operation_model_output,
)

REMOTE_PROVIDER_OPENAI = "openai"
REMOTE_PROVIDER_PGPT = "pgpt"
PGPT_ANALYSIS_DEFAULT_MODEL = "gpt-4o"
PGPT_FAST_TEST_DEFAULT_MODEL = "gpt-4o-mini"


class ModelGatewayError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        provider_error: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider_error = dict(provider_error or {})


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

    def plan_sp_operation_model(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        ...

    def draft_ai_java_mybatis_pack(
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
    if normalized in {AI_DRAFT_PACK_MODEL_PROFILE_ID, "ai-draft-pack", "draft-pack"}:
        if provider == REMOTE_PROVIDER_PGPT:
            model = os.getenv("PGPT_MODEL_ANALYSIS", PGPT_ANALYSIS_DEFAULT_MODEL).strip()
            model = model or PGPT_ANALYSIS_DEFAULT_MODEL
            reasoning_effort = "none"
        else:
            model = (
                os.getenv("OPENAI_MODEL_AI_DRAFT_PACK", "").strip()
                or os.getenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5").strip()
                or "gpt-5.5"
            )
            reasoning_effort = (
                os.getenv("OPENAI_REASONING_EFFORT_AI_DRAFT_PACK", "").strip()
                or os.getenv("OPENAI_REASONING_EFFORT_ANALYSIS", "medium").strip()
                or "medium"
            )
        return ModelProfile(
            profile_id=AI_DRAFT_PACK_MODEL_PROFILE_ID,
            model=model,
            registry_ref=ai_draft_pack_model_registry_ref(model),
            reasoning_effort=reasoning_effort,
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
        gateway = OpenAIModelGateway()
        from ai_agent_runtime.framework_runtime import build_model_gateway_runtime_from_env

        return build_model_gateway_runtime_from_env(model_gateway=gateway)
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
        sp_operation_model_by_target_ref: Mapping[str, Any] | None = None,
        ai_draft_pack_by_target_ref: Mapping[str, Any] | None = None,
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
        self._sp_operation_model_by_target_ref = {
            target_ref: validate_sp_operation_model_output(output).to_storage_dict()
            for target_ref, output in (sp_operation_model_by_target_ref or {}).items()
        }
        self._ai_draft_pack_by_target_ref = {
            target_ref: validate_ai_java_mybatis_draft_pack_output(output).to_storage_dict()
            for target_ref, output in (ai_draft_pack_by_target_ref or {}).items()
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

    def plan_sp_operation_model(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        raw_output = self._sp_operation_model_by_target_ref.get(target_ref) or (
            _default_fake_sp_operation_model_output(
                allowed_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
                target_ref=target_ref,
            )
        )
        output = validate_sp_operation_model_output(raw_output)
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
            provider_request_id="fake-sp-operation-model",
        )

    def draft_ai_java_mybatis_pack(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        target_ref = str(prompt.metadata.get("targetRef") or "")
        raw_output = self._ai_draft_pack_by_target_ref.get(target_ref) or (
            _default_fake_ai_draft_pack_output(
                allowed_refs=prompt.metadata.get("allowedEvidenceRefs") or (),
                prompt_payload=_prompt_payload(prompt),
                target_ref=target_ref,
            )
        )
        output = validate_ai_java_mybatis_draft_pack_output(raw_output)
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
            provider_request_id="fake-ai-draft-pack",
        )


def _default_fake_semantic_output() -> dict[str, Any]:
    return {
        "businessRules": [
            {
                "category": "LLM_SEMANTIC_SUMMARY",
                "summary": (
                    "Fake model gateway 초안 의미 요약: metadata and static analysis "
                    "were used to create a draft semantic summary."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": ["metadata.snapshot", "static.analysis"],
            }
        ],
        "modernizationPoints": [
            {
                "code": "REVIEW_SQL_BEHAVIOR_BEFORE_CONVERSION",
                "summary": (
                    "Java/MyBatis 珥덉븞 肄붾뱶濡??꾪솚?섍린 ?꾩뿉 procedure ?숈옉??寃?좏빐???⑸땲??"
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "riskFlags": [
            {
                "code": "LLM_OUTPUT_REQUIRES_HUMAN_REVIEW",
                "severity": "WARNING",
                "summary": "LLM 異붾줎? ?뺤씤??硫뷀??곗씠??洹쇨굅濡?痍④툒?섏? ?딆뒿?덈떎.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_INFERENCE_REVIEW_REQUIRED",
                "message": "LLM??異붾줎???섎? ?뺣낫??validation caveat濡??좎??⑸땲??",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["prompt.inputHash"],
            }
        ],
        "conversionGuidance": [
            {
                "code": "DRAFT_JAVA_MYBATIS_READINESS",
                "summary": (
                    "Java/MyBatis 珥덉븞???곸슜?섍린 ??寃곗젙濡좎쟻 硫뷀??곗씠?곗? validation caveat瑜?"
                    "諛섎뱶???뺤씤?댁빞 ?⑸땲??"
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "migrationGuideInsights": [
            {
                "section": "migration_strategy",
                "summary": (
                    "媛?대뱶 claim? evidence? ?곌껐?섍퀬, 誘몄????꾪솚 claim? REVIEW_REQUIRED濡?"
                    "?쒖떆?⑸땲??"
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["metadata.procedureDefinitionHash"],
            }
        ],
        "assumptions": [
            "Fake gateway瑜??ъ슜?덉쑝硫??몃? OpenAI API ?붿껌? 蹂대궡吏 ?딆븯?듬땲??",
            "LLM 異붾줎? raw prompt??SQL text ?놁씠 援ъ“??異쒕젰?쇰줈留???λ맗?덈떎.",
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
            "Fake model gateway 초안 메타데이터 분석: sanitized MCP evidence was "
            "used for a review-required draft metadata analysis."
        ),
        "objectInsights": [
            {
                "code": "METADATA_EVIDENCE_SUMMARY",
                "objectRef": target_ref or "metadata.analysis",
                "summary": (
                    "異붾줎??援ъ“瑜??ъ슜?섍린 ?꾩뿉 ?쎄린 ?꾩슜 硫뷀??곗씠??evidence瑜?寃?좏빐???⑸땲??"
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
                            "寃곗젙濡좎쟻 硫뷀??곗씠??profile怨?evidence caveat瑜??뺤씤?섍린 ?꾧퉴吏 "
                            "DTO readiness??draft-only濡??좎??⑸땲??"
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
                "reviewReasons": [
                    "Fake gateway??evidence ref 踰붿쐞瑜??섏뼱 DTO shape瑜??뺤젙?????놁뒿?덈떎."
                ],
                "evidenceRefs": evidence_refs,
            }
        ],
        "reviewMarkers": [
            {
                "code": "LLM_METADATA_ANALYSIS_REVIEW_REQUIRED",
                "message": "Metadata LLM 異붾줎? REVIEW_REQUIRED 蹂댁“ ?뺣낫濡??좎??⑸땲??",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "assumptions": [
            "Fake gateway瑜??ъ슜?덉쑝硫??몃? OpenAI API ?붿껌? 蹂대궡吏 ?딆븯?듬땲??",
            "?덉쟾?섏? ?딆? source text, sample record, secret-like 媛믪? ?쒖쇅?덉뒿?덈떎.",
        ],
    }


def _default_fake_sp_operation_model_output(
    *,
    allowed_refs: Any,
    target_ref: str,
) -> dict[str, Any]:
    refs = [str(ref) for ref in allowed_refs if str(ref).strip()]
    evidence_refs = refs[:1] or ["metadata.operation_model.no_fact"]
    normalized_target_ref = target_ref or "sp.operation.review_required"
    return {
        "schemaVersion": "SpOperationModel.v0.1",
        "contractTarget": "SpOperationModel",
        "targetRef": normalized_target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "operations": [
            {
                "operationId": "reviewRequiredOperation",
                "crudFlag": "REVIEW_REQUIRED",
                "title": "Operation model review required",
                "summary": "Fake gateway fallback operation model requires fixture evidence.",
                "branchCondition": {
                    "expression": "REVIEW_REQUIRED",
                    "variables": [],
                    "evidenceRefs": evidence_refs,
                    "status": "REVIEW_REQUIRED",
                },
                "statementRefs": ["stmt.review_required"],
                "dtoBlueprintRefs": ["OperationModelReviewRequired"],
                "stateTransitions": [],
                "riskMarkers": ["OPERATION_MODEL_FIXTURE_REVIEW_REQUIRED"],
                "evidenceRefs": evidence_refs,
                "status": "REVIEW_REQUIRED",
            }
        ],
        "statementEvidence": [
            {
                "statementId": "stmt.review_required",
                "operation": "VALIDATE",
                "targetRef": normalized_target_ref,
                "phase": "review_required",
                "inputs": [],
                "outputs": [],
                "writes": [],
                "crossDatabase": False,
                "reviewMarkers": ["OPERATION_MODEL_FIXTURE_REVIEW_REQUIRED"],
                "evidenceRefs": evidence_refs,
                "status": "REVIEW_REQUIRED",
            }
        ],
        "dtoBlueprints": [
            {
                "name": "OperationModelReviewRequired",
                "role": "REVIEW_REQUIRED",
                "operationIds": ["reviewRequiredOperation"],
                "fields": [
                    {
                        "name": "reviewRequired",
                        "dbType": "varchar(4000)",
                        "source": "REVIEW_REQUIRED",
                        "required": False,
                        "evidenceRefs": evidence_refs,
                    }
                ],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": ["OPERATION_MODEL_FIXTURE_REVIEW_REQUIRED"],
            }
        ],
        "reviewMarkers": ["OPERATION_MODEL_FIXTURE_REVIEW_REQUIRED"],
        "evidenceRefs": evidence_refs,
        "assumptions": ["Fake gateway fallback is not a production operation model."],
    }


def _default_fake_ai_draft_pack_output(
    *,
    allowed_refs: Any,
    prompt_payload: Mapping[str, Any] | None = None,
    target_ref: str,
) -> dict[str, Any]:
    refs = [str(ref) for ref in allowed_refs if str(ref).strip()]
    evidence_refs = refs[:1] or ["metadata.ai_draft_pack.no_fact"]
    normalized_target_ref = target_ref or "sp.ai_draft_pack.review_required"
    prompt_payload = dict(prompt_payload or {})
    expected_inventory = [
        dict(item)
        for item in prompt_payload.get("expectedInventory", [])
        if isinstance(item, Mapping)
    ]
    quality_gates = (
        dict(prompt_payload.get("qualityGates"))
        if isinstance(prompt_payload.get("qualityGates"), Mapping)
        else None
    )
    package_context = _fake_java_package_context(prompt_payload)
    model_package = package_context["modelPackage"]
    service_package = package_context["servicePackage"]
    mapper_package = package_context["mapperPackage"]
    draft_criteria_fqcn = f"{model_package}.DraftSearchCriteria"
    draft_row_fqcn = f"{model_package}.DraftSearchRow"
    draft_mapper_fqcn = f"{mapper_package}.DraftMapper"
    review_markers = [
        "P42_AI_DRAFT_PACK_REVIEW_REQUIRED",
        "CROSS_DB_WRITE_REVIEW_REQUIRED",
        "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
        "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
        "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
    ]
    if expected_inventory and quality_gates:
        return {
            "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
            "contractTarget": "AiJavaMyBatisDraftPack",
            "targetRef": normalized_target_ref,
            "sourcePolicy": "sanitized_facts_only",
            "productionReady": False,
            "files": [
                _fake_ai_draft_pack_file(
                    item,
                    evidence_refs=evidence_refs,
                    review_markers=review_markers,
                    package_context=package_context,
                )
                for item in expected_inventory
            ],
            "evidenceRefs": evidence_refs,
            "reviewMarkers": list(
                dict.fromkeys(
                    [
                        *review_markers,
                        *[
                            str(marker)
                            for marker in quality_gates.get("requiredReviewMarkers", [])
                            if str(marker).strip()
                        ],
                    ]
                )
            ),
            "qualityGates": quality_gates,
            "assumptions": ["Fake gateway materialized the expected inventory as draft-only."],
        }
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": normalized_target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": [
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/DraftSearchCriteria.java",
                "role": "QUERY_DTO",
                "className": "DraftSearchCriteria",
                "content": (
                    f"package {model_package};\n\n"
                    "public class DraftSearchCriteria {\n"
                    "    // REVIEW_REQUIRED DraftSearchCriteria\n"
                    "    private String draftEvidenceKey;\n\n"
                    "    public String getDraftEvidenceKey() {\n"
                    "        return draftEvidenceKey;\n"
                    "    }\n\n"
                    "    public void setDraftEvidenceKey(String draftEvidenceKey) {\n"
                    "        this.draftEvidenceKey = draftEvidenceKey;\n"
                    "    }\n"
                    "}"
                ),
                "operationIds": ["reviewDraft"],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": review_markers,
                "requiredFields": ["draftEvidenceKey"],
            },
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/DraftSearchRow.java",
                "role": "RESULT_DTO",
                "className": "DraftSearchRow",
                "content": (
                    f"package {model_package};\n\n"
                    "public class DraftSearchRow {\n"
                    "    // REVIEW_REQUIRED DraftSearchRow\n"
                    "    private String draftEvidenceKey;\n\n"
                    "    public String getDraftEvidenceKey() {\n"
                    "        return draftEvidenceKey;\n"
                    "    }\n\n"
                    "    public void setDraftEvidenceKey(String draftEvidenceKey) {\n"
                    "        this.draftEvidenceKey = draftEvidenceKey;\n"
                    "    }\n"
                    "}"
                ),
                "operationIds": ["reviewDraft"],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": review_markers,
                "requiredFields": ["draftEvidenceKey"],
            },
            {
                "artifactType": "SERVICE_DRAFT",
                "path": "service/DraftService.java",
                "role": "SERVICE",
                "className": "DraftService",
                "content": (
                    f"package {service_package};\n\n"
                    f"import {draft_criteria_fqcn};\n"
                    f"import {draft_mapper_fqcn};\n\n"
                    "public class DraftService {\n"
                    "    private final DraftMapper mapper;\n"
                    "    public DraftService(DraftMapper mapper) { this.mapper = mapper; }\n"
                    "    // REVIEW_REQUIRED DraftSearchCriteria DraftSearchRow\n"
                    "    public Object reviewDraft(DraftSearchCriteria criteria) {\n"
                    "        java.util.Objects.requireNonNull(criteria, \"criteria\");\n"
                    "        Object result = mapper.reviewDraft(criteria);\n"
                    "        return result;\n"
                    "    }\n"
                    "}"
                ),
                "operationIds": ["reviewDraft"],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": review_markers,
                "references": ["DraftSearchCriteria", "DraftSearchRow"],
            },
            {
                "artifactType": "MAPPER_INTERFACE",
                "path": "mapper/DraftMapper.java",
                "role": "MAPPER_INTERFACE",
                "className": "DraftMapper",
                "content": (
                    f"package {mapper_package};\n\n"
                    f"import {draft_criteria_fqcn};\n\n"
                    "public interface DraftMapper {\n"
                    "    // REVIEW_REQUIRED DraftSearchCriteria DraftSearchRow\n"
                    "    Object reviewDraft(DraftSearchCriteria criteria);\n"
                    "}"
                ),
                "operationIds": ["reviewDraft"],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": review_markers,
                "references": ["DraftSearchCriteria", "DraftSearchRow"],
            },
            {
                "artifactType": "MAPPER_XML",
                "path": "mapper/DraftMapperSQL.xml",
                "role": "MAPPER_XML",
                "className": "DraftMapperSQL",
                "content": (
                    f'<mapper namespace="{draft_mapper_fqcn}">\n'
                    "  <!-- REVIEW_REQUIRED DraftSearchCriteria DraftSearchRow -->\n"
                    f'  <resultMap id="DraftSearchRowMap" type="{draft_row_fqcn}">\n'
                    '    <result column="DRAFT_EVIDENCE_KEY" property="draftEvidenceKey"/>\n'
                    "  </resultMap>\n"
                    f'  <select id="reviewDraft" parameterType="{draft_criteria_fqcn}" '
                    'resultMap="DraftSearchRowMap">\n'
                    "    SELECT DRAFT_EVIDENCE_KEY FROM dbo.DraftEvidence\n"
                    "    WHERE DRAFT_EVIDENCE_KEY = #{draftEvidenceKey}\n"
                    "  </select>\n"
                    "</mapper>"
                ),
                "operationIds": ["reviewDraft"],
                "evidenceRefs": evidence_refs,
                "reviewMarkers": review_markers,
                "references": ["DraftSearchCriteria", "DraftSearchRow"],
            },
        ],
        "evidenceRefs": evidence_refs,
        "reviewMarkers": review_markers,
        "qualityGates": {
            "requiredDtoClasses": ["DraftSearchCriteria", "DraftSearchRow"],
            "requiredServiceMethods": ["reviewDraft"],
            "requiredMapperMethods": ["reviewDraft"],
            "requiredReviewMarkers": review_markers,
            "blockerPatterns": ["OperationModelReviewRequired"],
            "blankContentIsBlocker": True,
            "dtoCollapseIsBlocker": True,
            "fallbackSkeletonPersistenceAllowedOnFailure": False,
        },
        "assumptions": ["Fake gateway fallback is draft-only and requires review."],
    }


def _prompt_payload(prompt: RenderedPrompt) -> dict[str, Any]:
    try:
        payload = json.loads(prompt.user_prompt)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _prompt_operation_statement_evidence(prompt: RenderedPrompt) -> list[dict[str, Any]]:
    payload = _prompt_payload(prompt)
    statements = payload.get("statementEvidence")
    if not isinstance(statements, list):
        return []
    return [dict(item) for item in statements if isinstance(item, Mapping)]


def _sp_operation_model_text_with_statement_evidence_defaults(
    output_text: str,
    *,
    statement_defaults: Sequence[Mapping[str, Any]],
) -> str:
    if not statement_defaults:
        return output_text
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return output_text
    if not isinstance(payload, dict):
        return output_text

    operations = payload.get("operations")
    if not isinstance(operations, list):
        return output_text
    default_statements = [dict(item) for item in statement_defaults if isinstance(item, Mapping)]
    default_by_id = {
        str(item.get("statementId") or ""): item
        for item in default_statements
        if str(item.get("statementId") or "")
    }
    default_aliases = _operation_statement_ref_aliases(default_statements)
    existing_statements = payload.get("statementEvidence")
    if not isinstance(existing_statements, list):
        existing_statements = []
    existing_statement_maps: list[dict[str, Any]] = []
    for item in existing_statements:
        if not isinstance(item, Mapping):
            continue
        statement_id = str(item.get("statementId") or "")
        canonical_id = default_aliases.get(statement_id, statement_id)
        if canonical_id in default_by_id:
            existing_statement_maps.append(dict(default_by_id[canonical_id]))
            continue
        copied = dict(item)
        if canonical_id != statement_id:
            copied["statementId"] = canonical_id
        existing_statement_maps.append(copied)
    aliases = _operation_statement_ref_aliases(
        [*existing_statement_maps, *default_statements]
    )
    existing_ids = {
        str(item.get("statementId") or "")
        for item in existing_statement_maps
        if str(item.get("statementId") or "")
    }
    referenced_default_ids: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        key = "statementRefs" if "statementRefs" in operation else "statement_refs"
        refs = operation.get(key)
        if not isinstance(refs, list):
            continue
        normalized_refs: list[str] = []
        for ref in refs:
            ref_text = _operation_model_string_value(
                ref,
                candidate_keys=("statementId", "statement_id", "id", "ref"),
            )
            if not ref_text:
                continue
            mapped_ref = aliases.get(ref_text, ref_text)
            if mapped_ref in default_by_id:
                referenced_default_ids.add(mapped_ref)
            if mapped_ref not in normalized_refs:
                normalized_refs.append(mapped_ref)
        operation["statementRefs"] = normalized_refs
        if key != "statementRefs":
            operation.pop(key, None)

    for statement_id in sorted(referenced_default_ids - existing_ids):
        existing_statement_maps.append(dict(default_by_id[statement_id]))
    payload["statementEvidence"] = existing_statement_maps
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _operation_statement_ref_aliases(
    statements: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for statement in statements:
        statement_id = str(statement.get("statementId") or "")
        if not statement_id:
            continue
        operation = str(statement.get("operation") or "").lower()
        aliases[statement_id] = statement_id
        suffix = statement_id.rsplit(".", 1)[-1]
        if suffix:
            aliases[suffix] = statement_id
            if operation:
                aliases[f"stmt.{operation}.{suffix}"] = statement_id
        for ref in statement.get("evidenceRefs", []) or []:
            ref_text = str(ref).strip()
            if not ref_text:
                continue
            aliases[ref_text] = statement_id
            ref_suffix = ref_text.rsplit(".", 1)[-1]
            if ref_suffix:
                aliases[ref_suffix] = statement_id
                if operation:
                    aliases[f"stmt.{operation}.{ref_suffix}"] = statement_id
                    aliases[f"stmt.{operation}.{ref_text}"] = statement_id
    return aliases


def _fake_ai_draft_pack_file(
    item: Mapping[str, Any],
    *,
    evidence_refs: Sequence[str],
    review_markers: Sequence[str],
    package_context: Mapping[str, str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifactType": str(item.get("artifactType") or ""),
        "path": str(item.get("path") or ""),
        "role": str(item.get("role") or ""),
        "className": str(item.get("className") or "DraftFile"),
        "operationIds": [
            str(ref)
            for ref in item.get("operationIds", [])
            if str(ref).strip()
        ]
        or ["reviewDraft"],
        "evidenceRefs": [
            str(ref)
            for ref in item.get("evidenceRefs", [])
            if str(ref).strip()
        ]
        or list(evidence_refs),
        "reviewMarkers": [
            str(marker)
            for marker in item.get("reviewMarkers", [])
            if str(marker).strip()
        ]
        or list(review_markers),
    }
    for key in ("dtoRole", "requiredFields", "references"):
        if key in item:
            value = item[key]
            payload[key] = (
                list(value)
                if isinstance(value, Sequence) and not isinstance(value, str | bytes)
                else value
            )
    payload["content"] = _fake_ai_draft_pack_content(
        payload,
        package_context=package_context,
    )
    return payload


def _fake_ai_draft_pack_content(
    file: Mapping[str, Any],
    *,
    package_context: Mapping[str, str],
) -> str:
    artifact_type = str(file.get("artifactType") or "")
    class_name = str(file.get("className") or "DraftFile")
    model_package = str(package_context.get("modelPackage") or "")
    service_package = str(package_context.get("servicePackage") or "")
    mapper_package = str(package_context.get("mapperPackage") or "")
    markers = " ".join(str(marker) for marker in file.get("reviewMarkers", []) if str(marker))
    methods = [
        str(method)
        for method in file.get("operationIds", [])
        if str(method).strip()
    ] or ["reviewDraft"]
    references = " ".join(
        str(reference)
        for reference in file.get("references", [])
        if str(reference).strip()
    )
    if artifact_type == "DTO_DRAFT":
        field_names = [
            str(field)
            for field in file.get("requiredFields", [])
            if str(field).strip()
        ] or ["draftEvidenceKey"]
        fields = "\n".join(f"    private String {field};" for field in field_names)
        accessors = "\n\n".join(_fake_java_string_accessors(field) for field in field_names)
        return (
            f"package {model_package};\n\n"
            f"public class {class_name} {{\n"
            f"    // {markers} draft DTO.\n"
            f"{fields}\n\n"
            f"{accessors}\n"
            "}"
        )
    if artifact_type == "SERVICE_DRAFT":
        method_text = "\n".join(
            f"    public Object {method}(Object command) {{\n"
            '        java.util.Objects.requireNonNull(command, "command");\n'
            f"        Object result = mapper.{method}(command);\n"
            "        return result;\n"
            "    }"
            for method in methods
        )
        mapper_class = class_name[:-7] + "Mapper" if class_name.endswith("Service") else "DraftMapper"
        return (
            f"package {service_package};\n\n"
            f"import {mapper_package}.{mapper_class};\n\n"
            f"public class {class_name} {{\n"
            f"    private final {mapper_class} mapper;\n"
            f"    public {class_name}({mapper_class} mapper) {{ this.mapper = mapper; }}\n"
            f"    // REVIEW_REQUIRED {references}\n{method_text}\n}}"
        )
    if artifact_type == "MAPPER_INTERFACE":
        method_text = "\n".join(f"    Object {method}(Object command);" for method in methods)
        return (
            f"package {mapper_package};\n\n"
            f"public interface {class_name} {{\n"
            f"    // REVIEW_REQUIRED {references}\n{method_text}\n}}"
        )
    if artifact_type == "MAPPER_XML":
        refs = [
            str(reference)
            for reference in file.get("references", [])
            if str(reference).strip()
        ]
        parameter_type = _fake_dto_fqcn(refs[0], package_context) if refs else ""
        result_type = (
            _fake_dto_fqcn(refs[1] if len(refs) > 1 else refs[0], package_context)
            if refs
            else ""
        )
        result_map = (
            f'  <resultMap id="DraftResultMap" type="{result_type}">\n'
            '    <result column="DRAFT_EVIDENCE_KEY" property="draftEvidenceKey"/>\n'
            "  </resultMap>\n"
            if result_type
            else ""
        )
        statement_parts = []
        for method in methods:
            parameter_attr = f' parameterType="{parameter_type}"' if parameter_type else ""
            if method.lower().startswith(("read", "search", "select")) and result_type:
                statement_parts.append(
                    f'  <select id="{method}"{parameter_attr} resultMap="DraftResultMap">\n'
                    "    SELECT DRAFT_EVIDENCE_KEY FROM dbo.DraftEvidence\n"
                    "    WHERE DRAFT_EVIDENCE_KEY = #{draftEvidenceKey}\n"
                    "  </select>"
                )
            else:
                statement_parts.append(
                    f'  <update id="{method}"{parameter_attr}>\n'
                    "    UPDATE dbo.DraftEvidence\n"
                    "    SET DRAFT_EVIDENCE_VALUE = #{draftEvidenceKey}\n"
                    "    WHERE DRAFT_EVIDENCE_KEY = #{draftEvidenceKey}\n"
                    "  </update>"
                )
        statement_text = "\n".join(statement_parts)
        namespace = class_name[:-3] if class_name.endswith("SQL") else class_name
        return (
            f'<mapper namespace="{mapper_package}.{namespace}">\n'
            f"  <!-- REVIEW_REQUIRED {references} -->\n"
            f"{result_map}"
            f"{statement_text}\n"
            "</mapper>"
        )
    return f"// REVIEW_REQUIRED {class_name} {markers} {references}"


def _fake_dto_fqcn(class_name: str, package_context: Mapping[str, str]) -> str:
    return f"{package_context['modelPackage']}.{class_name}"


def _fake_java_package_context(prompt_payload: Mapping[str, Any]) -> dict[str, str]:
    sanitized_context = prompt_payload.get("sanitizedDraftContext")
    raw_context = (
        sanitized_context.get("javaPackageContext")
        if isinstance(sanitized_context, Mapping)
        else None
    )
    raw_package_context = raw_context if isinstance(raw_context, Mapping) else {}
    model_package = _fake_valid_java_package(
        str(raw_package_context.get("modelPackage") or raw_package_context.get("dtoPackage") or "")
    )
    service_package = _fake_valid_java_package(
        str(raw_package_context.get("servicePackage") or "")
    )
    mapper_package = _fake_valid_java_package(str(raw_package_context.get("mapperPackage") or ""))
    return {
        "modelPackage": model_package or "com.pec.draft.workflow.draft.model",
        "servicePackage": service_package or "com.pec.draft.workflow.draft.service",
        "mapperPackage": mapper_package or "com.pec.draft.workflow.draft.mapper",
    }


def _fake_valid_java_package(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(
        r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*",
        text,
    ):
        return text
    return ""


def _fake_java_string_accessors(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public String get{suffix}() {{\n"
        f"        return {field};\n"
        "    }\n\n"
        f"    public void set{suffix}(String {field}) {{\n"
        f"        this.{field} = {field};\n"
        "    }"
    )


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

    def plan_sp_operation_model(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        allowed_refs = prompt.metadata.get("allowedEvidenceRefs") or ()
        statement_defaults = _prompt_operation_statement_evidence(prompt)
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="sp_operation_model",
            schema=sp_operation_model_output_schema(
                allowed_evidence_refs=allowed_refs,
            ),
            parser=lambda output_text: parse_sp_operation_model_json(
                _sp_operation_model_text_with_statement_evidence_defaults(
                    output_text,
                    statement_defaults=statement_defaults,
                ),
                allowed_evidence_refs=allowed_refs,
            ),
            invalid_code="OPENAI_SP_OPERATION_MODEL_INVALID",
        )

    def draft_ai_java_mybatis_pack(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        allowed_refs = prompt.metadata.get("allowedEvidenceRefs") or ()
        quality_gates = _prompt_ai_draft_pack_quality_gates(prompt)
        return self._invoke_structured_output(
            prompt=prompt,
            profile=profile,
            schema_name="ai_java_mybatis_draft_pack",
            schema=ai_java_mybatis_draft_pack_output_schema(
                allowed_evidence_refs=allowed_refs,
            ),
            parser=lambda output_text: parse_ai_java_mybatis_draft_pack_json(
                _ai_draft_pack_text_with_quality_gate_defaults(
                    output_text,
                    quality_gates=quality_gates,
                ),
                allowed_evidence_refs=allowed_refs,
            ),
            invalid_code="OPENAI_AI_DRAFT_PACK_INVALID",
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
        if (
            prompt.metadata.get("procedureDefinitionIncluded")
            or prompt.metadata.get("sourceContextIncluded")
        ) and (
            os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1"
        ):
            raise ModelGatewayError(
                "LLM_ALLOW_SP_TEXT=1 is required before sending SP source text.",
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
        retry_component: dict[str, Any] | None = None
        try:
            (
                response_payload,
                output,
                normalizer_components,
                provider_request_id,
            ) = self._post_and_parse_structured(
                responses_url=responses_url,
                api_key=api_key,
                payload=payload,
                parser=parser,
                schema_name=schema_name,
                allowed_tool_names=prompt.metadata.get("toolNames") or (),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            if self.provider != REMOTE_PROVIDER_PGPT:
                raise ModelGatewayError(
                    "OpenAI response did not match the required structured output schema.",
                    code=invalid_code,
                    provider_error=_parser_error_summary(exc, invalid_code=invalid_code),
                ) from exc
            try:
                retry_component = {
                    "component": "pgpt_structured_output_retry",
                    "status": "SUCCEEDED",
                    "action": "retried_json_only_after_invalid_output",
                }
                (
                    response_payload,
                    output,
                    normalizer_components,
                    provider_request_id,
                ) = self._post_and_parse_structured(
                    responses_url=responses_url,
                    api_key=api_key,
                    payload=_pgpt_retry_payload(
                        prompt=prompt,
                        profile=profile,
                        schema_name=schema_name,
                    ),
                    parser=parser,
                    schema_name=schema_name,
                    allowed_tool_names=prompt.metadata.get("toolNames") or (),
                )
            except (json.JSONDecodeError, ValueError) as retry_exc:
                raise ModelGatewayError(
                    "OpenAI response did not match the required structured output schema.",
                    code=invalid_code,
                    provider_error=_parser_error_summary(
                        retry_exc,
                        invalid_code=invalid_code,
                    ),
                ) from retry_exc
        except httpx.HTTPStatusError as exc:
            raise ModelGatewayError(
                "OpenAI Responses API returned an error.",
                code=_http_error_code(exc.response.status_code),
                provider_error=_provider_error_summary(exc.response),
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

        structured_output = output.to_storage_dict()
        if retry_component is not None:
            normalizer_components = [retry_component, *normalizer_components]
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
            provider_request_id=provider_request_id,
            component_invocations=tuple(normalizer_components),
        )

    def _post_and_parse_structured(
        self,
        *,
        responses_url: str,
        api_key: str,
        payload: dict[str, Any],
        parser,
        schema_name: str,
        allowed_tool_names: Sequence[str],
    ) -> tuple[dict[str, Any], Any, list[dict[str, Any]], str | None]:
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
            allowed_tool_names=allowed_tool_names,
            provider=self.provider,
        )
        provider_request_id = str(
            response_payload.get("id") or response.headers.get("x-request-id") or ""
        ) or None
        return response_payload, output, normalizer_components, provider_request_id

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


def _pgpt_retry_payload(
    *,
    prompt: RenderedPrompt,
    profile: ModelProfile,
    schema_name: str,
) -> dict[str, Any]:
    root_keys = _retry_root_keys(schema_name)
    root_key_text = ", ".join(root_keys)
    retry_instruction = (
        "The previous provider response could not be parsed as the required JSON object. "
        "Return exactly one JSON object and no prose, markdown fence, heading, or explanation. "
        f"The object must include these top-level keys: {root_key_text}. "
        "Use empty arrays when a section has no supported claim. Preserve machine identifiers "
        "and evidenceRefs exactly."
    )
    if schema_name == "ai_java_mybatis_draft_pack":
        retry_instruction = (
            f"{retry_instruction} The files array must contain file objects with keys "
            "artifactType, path, role, className, content, operationIds, evidenceRefs, "
            "reviewMarkers, dtoRole, requiredFields, references, and qualityScore. "
            "Every content value must be a non-empty Java or Mapper XML draft string."
        )
    return {
        "model": profile.model,
        "instructions": f"{prompt.system_prompt}\n\n{retry_instruction}",
        "input": [{"role": "user", "content": prompt.user_prompt}],
    }


def _retry_root_keys(schema_name: str) -> tuple[str, ...]:
    if schema_name == "llm_semantic_analysis":
        return _SEMANTIC_ROOT_KEYS
    if schema_name in {"metadata_tool_plan", "platform_tool_plan"}:
        return ("toolRequests", "assumptions", "reviewMarkers")
    if schema_name == "metadata_analysis":
        return (
            "summary",
            "objectInsights",
            "insightGroups",
            "dtoReadiness",
            "reviewMarkers",
            "assumptions",
        )
    if schema_name == "sp_operation_model":
        return (
            "schemaVersion",
            "contractTarget",
            "targetRef",
            "sourcePolicy",
            "productionReady",
            "operations",
            "statementEvidence",
            "dtoBlueprints",
            "reviewMarkers",
            "evidenceRefs",
            "assumptions",
        )
    if schema_name == "ai_java_mybatis_draft_pack":
        return (
            "schemaVersion",
            "contractTarget",
            "targetRef",
            "sourcePolicy",
            "productionReady",
            "files",
            "evidenceRefs",
            "reviewMarkers",
            "qualityGates",
            "assumptions",
        )
    return ("structuredOutput",)


def _provider_error_summary(response: httpx.Response) -> dict[str, str]:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    error = payload.get("error")
    source = error if isinstance(error, Mapping) else payload
    summary: dict[str, str] = {}
    for key in ("type", "code", "param", "message"):
        if key in source and source[key] is not None:
            value = _sanitize_provider_error_value(source[key], key=key)
            if value:
                summary[key] = value
    return summary


def _parser_error_summary(exc: Exception, *, invalid_code: str) -> dict[str, str]:
    summary = {
        "type": exc.__class__.__name__,
        "code": invalid_code,
    }
    if isinstance(exc, json.JSONDecodeError):
        summary["message"] = str(exc)[:300]
    elif isinstance(exc, AiDraftPackValidationError):
        summary["message"] = "AiJavaMyBatisDraftPack validation failed."
        summary["findingCount"] = str(len(exc.findings))
        findings = _sanitized_parser_findings(exc.findings)
        if findings:
            summary["findings"] = " | ".join(findings)
    elif isinstance(exc, OperationModelValidationError):
        summary["message"] = "SpOperationModel validation failed."
        summary["findingCount"] = str(len(exc.findings))
        findings = _sanitized_parser_findings(exc.findings)
        if findings:
            summary["findings"] = " | ".join(findings)
    else:
        summary["message"] = str(exc)[:300]
    return summary


def _prompt_ai_draft_pack_quality_gates(prompt: RenderedPrompt) -> dict[str, Any]:
    try:
        payload = json.loads(prompt.user_prompt)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    quality_gates = payload.get("qualityGates")
    return dict(quality_gates) if isinstance(quality_gates, Mapping) else {}


def _ai_draft_pack_text_with_quality_gate_defaults(
    output_text: str,
    *,
    quality_gates: Mapping[str, Any],
) -> str:
    if not quality_gates:
        return output_text
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return output_text
    if not isinstance(payload, dict):
        return output_text
    payload["qualityGates"] = dict(quality_gates)
    required_markers = [
        str(marker)
        for marker in quality_gates.get("requiredReviewMarkers", [])
        if str(marker).strip()
    ]
    if required_markers:
        raw_markers = payload.get("reviewMarkers", [])
        if not isinstance(raw_markers, list):
            raw_markers = [raw_markers]
        existing_markers = [
            marker
            for marker in (
                _operation_model_string_value(
                    raw_marker,
                    candidate_keys=("code", "marker", "name", "message", "summary"),
                )
                for raw_marker in raw_markers
            )
            if marker
        ]
        payload["reviewMarkers"] = list(dict.fromkeys([*existing_markers, *required_markers]))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sanitized_parser_findings(findings: Sequence[str]) -> list[str]:
    safe: list[str] = []
    for finding in findings[:8]:
        text = str(finding)
        safe.append(text[:220])
    return safe


def _sanitize_provider_error_value(value: Any, *, key: str) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        text = str(value)
    text = " ".join(text.split())
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]", text)
    text = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)\b\s*[:=]\s*['\"]?[^,'\"\s}]+",
        r"\1=[REDACTED]",
        text,
    )
    if key == "message" and _looks_like_raw_sql(text):
        return "[REDACTED_PROVIDER_MESSAGE_WITH_POTENTIAL_SQL]"
    max_length = 500
    if len(text) > max_length:
        text = f"{text[:max_length]}...[truncated]"
    return text


def _looks_like_raw_sql(text: str) -> bool:
    return bool(
        re.search(r"(?i)\b(create|alter)\s+(procedure|proc|function|view|trigger)\b", text)
        or re.search(
            r"(?i)\b(select|insert|update|delete|merge)\b.{0,120}\b(from|into|set|using)\b",
            text,
        )
    )


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
    if provider == REMOTE_PROVIDER_PGPT and schema_name == "sp_operation_model":
        output_text, adapter_components = _pgpt_json_object_output_text(
            output_text,
            action="adapted_pgpt_sp_operation_model_output",
        )
    if provider == REMOTE_PROVIDER_PGPT and schema_name == "ai_java_mybatis_draft_pack":
        output_text, adapter_components = _pgpt_json_object_output_text(
            output_text,
            action="adapted_pgpt_ai_draft_pack_output",
        )
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
        if schema_name == "sp_operation_model":
            repaired, removed_paths = _operation_model_without_schema_drift(output_text)
            if not removed_paths:
                raise exc
            return (
                parser(json.dumps(repaired, ensure_ascii=False, separators=(",", ":"))),
                [
                    *adapter_components,
                    {
                        "component": "structured_output_normalizer",
                        "status": "SUCCEEDED",
                        "action": "normalized_sp_operation_model",
                        "removedFieldPaths": removed_paths,
                    },
                ],
            )
        if schema_name == "ai_java_mybatis_draft_pack":
            repaired, removed_paths = _ai_draft_pack_without_schema_drift(output_text)
            if not removed_paths:
                raise exc
            return (
                parser(json.dumps(repaired, ensure_ascii=False, separators=(",", ":"))),
                [
                    *adapter_components,
                    {
                        "component": "structured_output_normalizer",
                        "status": "SUCCEEDED",
                        "action": "normalized_ai_java_mybatis_draft_pack",
                        "removedFieldPaths": removed_paths,
                    },
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


_OPERATION_MODEL_ROOT_KEYS = {
    "schemaVersion",
    "contractTarget",
    "targetRef",
    "sourcePolicy",
    "productionReady",
    "operations",
    "statementEvidence",
    "dtoBlueprints",
    "reviewMarkers",
    "evidenceRefs",
    "assumptions",
}
_OPERATION_MODEL_OPERATION_KEYS = {
    "operationId",
    "crudFlag",
    "title",
    "summary",
    "branchCondition",
    "statementRefs",
    "dtoBlueprintRefs",
    "stateTransitions",
    "riskMarkers",
    "evidenceRefs",
    "status",
}
_OPERATION_MODEL_BRANCH_KEYS = {"expression", "variables", "evidenceRefs", "status"}
_OPERATION_MODEL_STATEMENT_KEYS = {
    "statementId",
    "operation",
    "targetRef",
    "phase",
    "inputs",
    "outputs",
    "writes",
    "crossDatabase",
    "reviewMarkers",
    "evidenceRefs",
    "status",
}
_OPERATION_MODEL_DTO_KEYS = {
    "name",
    "role",
    "operationIds",
    "fields",
    "evidenceRefs",
    "reviewMarkers",
}
_OPERATION_MODEL_DTO_FIELD_KEYS = {"name", "dbType", "source", "required", "evidenceRefs"}

_OPERATION_MODEL_ROOT_ALIASES = {
    "schema_version": "schemaVersion",
    "contract_target": "contractTarget",
    "target_ref": "targetRef",
    "source_policy": "sourcePolicy",
    "production_ready": "productionReady",
    "statement_evidence": "statementEvidence",
    "dto_blueprints": "dtoBlueprints",
    "review_markers": "reviewMarkers",
    "evidence_refs": "evidenceRefs",
}
_OPERATION_MODEL_OPERATION_ALIASES = {
    "operation_id": "operationId",
    "crud_flag": "crudFlag",
    "branch_condition": "branchCondition",
    "statement_refs": "statementRefs",
    "dto_blueprint_refs": "dtoBlueprintRefs",
    "state_transitions": "stateTransitions",
    "risk_markers": "riskMarkers",
    "reviewMarkers": "riskMarkers",
    "review_markers": "riskMarkers",
    "evidence_refs": "evidenceRefs",
}
_OPERATION_MODEL_BRANCH_ALIASES = {"evidence_refs": "evidenceRefs"}
_OPERATION_MODEL_STATEMENT_ALIASES = {
    "statement_id": "statementId",
    "target_ref": "targetRef",
    "cross_database": "crossDatabase",
    "review_markers": "reviewMarkers",
    "evidence_refs": "evidenceRefs",
}
_OPERATION_MODEL_DTO_ALIASES = {
    "className": "name",
    "class_name": "name",
    "dtoRole": "role",
    "dto_role": "role",
    "operation_ids": "operationIds",
    "review_markers": "reviewMarkers",
    "evidence_refs": "evidenceRefs",
}
_OPERATION_MODEL_DTO_FIELD_ALIASES = {
    "db_type": "dbType",
    "evidence_refs": "evidenceRefs",
}

_AI_DRAFT_PACK_ROOT_KEYS = {
    "schemaVersion",
    "contractTarget",
    "targetRef",
    "sourcePolicy",
    "productionReady",
    "files",
    "evidenceRefs",
    "reviewMarkers",
    "qualityGates",
    "assumptions",
}
_AI_DRAFT_PACK_FILE_KEYS = {
    "artifactType",
    "path",
    "role",
    "className",
    "content",
    "operationIds",
    "evidenceRefs",
    "reviewMarkers",
    "dtoRole",
    "requiredFields",
    "references",
    "qualityScore",
}
_AI_DRAFT_PACK_QUALITY_GATE_KEYS = {
    "requiredDtoClasses",
    "requiredServiceMethods",
    "requiredMapperMethods",
    "requiredReviewMarkers",
    "blockerPatterns",
    "blankContentIsBlocker",
    "dtoCollapseIsBlocker",
    "fallbackSkeletonPersistenceAllowedOnFailure",
}
_AI_DRAFT_PACK_ROOT_ALIASES = {
    "schema_version": "schemaVersion",
    "contract_target": "contractTarget",
    "target_ref": "targetRef",
    "source_policy": "sourcePolicy",
    "production_ready": "productionReady",
    "evidence_refs": "evidenceRefs",
    "review_markers": "reviewMarkers",
    "quality_gates": "qualityGates",
}
_AI_DRAFT_PACK_FILE_ALIASES = {
    "artifact_type": "artifactType",
    "class_name": "className",
    "operation_ids": "operationIds",
    "evidence_refs": "evidenceRefs",
    "review_markers": "reviewMarkers",
    "dto_role": "dtoRole",
    "required_fields": "requiredFields",
    "quality_score": "qualityScore",
}
_AI_DRAFT_PACK_QUALITY_GATE_ALIASES = {
    "required_dto_classes": "requiredDtoClasses",
    "required_service_methods": "requiredServiceMethods",
    "required_mapper_methods": "requiredMapperMethods",
    "required_review_markers": "requiredReviewMarkers",
    "blocker_patterns": "blockerPatterns",
    "blank_content_is_blocker": "blankContentIsBlocker",
    "dto_collapse_is_blocker": "dtoCollapseIsBlocker",
    "fallback_skeleton_persistence_allowed_on_failure": (
        "fallbackSkeletonPersistenceAllowedOnFailure"
    ),
}


def _ai_draft_pack_without_schema_drift(output_text: str) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return {}, []
    if not isinstance(payload, dict):
        return {}, []

    removed_paths: list[str] = []
    payload = _ai_draft_pack_payload_from_wrapper(payload, removed_paths=removed_paths)
    repaired = _aliased_mapping_without_extra_fields(
        payload,
        allowed_keys=_AI_DRAFT_PACK_ROOT_KEYS,
        aliases=_AI_DRAFT_PACK_ROOT_ALIASES,
        path="$",
        removed_paths=removed_paths,
    )
    repaired["files"] = _ai_draft_pack_files_without_schema_drift(
        repaired.get("files"),
        path="$.files",
        removed_paths=removed_paths,
    )
    repaired["evidenceRefs"] = _operation_model_string_list(
        repaired.get("evidenceRefs"),
        path="$.evidenceRefs",
        removed_paths=removed_paths,
        candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
    )
    repaired["reviewMarkers"] = _operation_model_string_list(
        repaired.get("reviewMarkers"),
        path="$.reviewMarkers",
        removed_paths=removed_paths,
        candidate_keys=("code", "marker", "name", "message", "summary"),
    )
    repaired["assumptions"] = _operation_model_string_list(
        repaired.get("assumptions"),
        path="$.assumptions",
        removed_paths=removed_paths,
        candidate_keys=("summary", "text", "message", "description"),
    )
    repaired["qualityGates"] = _ai_draft_pack_quality_gates_without_schema_drift(
        repaired.get("qualityGates"),
        path="$.qualityGates",
        removed_paths=removed_paths,
    )
    return repaired, sorted(set(removed_paths))


def _ai_draft_pack_payload_from_wrapper(
    payload: dict[str, Any],
    *,
    removed_paths: list[str],
) -> dict[str, Any]:
    if _looks_like_ai_draft_pack_payload(payload):
        return payload
    for key in ("aiDraftPack", "draftPack", "structuredOutput", "output", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict) and _looks_like_ai_draft_pack_payload(nested):
            removed_paths.append(f"$.{key}")
            return nested
    return payload


def _looks_like_ai_draft_pack_payload(payload: Mapping[str, Any]) -> bool:
    keys = set(payload) | {_AI_DRAFT_PACK_ROOT_ALIASES.get(key, key) for key in payload}
    return bool(keys & {"files", "qualityGates", "targetRef"})


def _ai_draft_pack_files_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    items = _operation_model_value_list(value, path=path, removed_paths=removed_paths)
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        repaired = _aliased_mapping_without_extra_fields(
            raw_item,
            allowed_keys=_AI_DRAFT_PACK_FILE_KEYS,
            aliases=_AI_DRAFT_PACK_FILE_ALIASES,
            path=item_path,
            removed_paths=removed_paths,
        )
        repaired["operationIds"] = _operation_model_string_list(
            repaired.get("operationIds"),
            path=f"{item_path}.operationIds",
            removed_paths=removed_paths,
            candidate_keys=("operationId", "operation_id", "id", "ref"),
        )
        repaired["evidenceRefs"] = _operation_model_string_list(
            repaired.get("evidenceRefs"),
            path=f"{item_path}.evidenceRefs",
            removed_paths=removed_paths,
            candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
        )
        repaired["reviewMarkers"] = _operation_model_string_list(
            repaired.get("reviewMarkers"),
            path=f"{item_path}.reviewMarkers",
            removed_paths=removed_paths,
            candidate_keys=("code", "marker", "name", "message", "summary"),
        )
        repaired["requiredFields"] = _operation_model_string_list(
            repaired.get("requiredFields"),
            path=f"{item_path}.requiredFields",
            removed_paths=removed_paths,
            candidate_keys=("name", "field", "column", "param", "parameter"),
        )
        repaired["references"] = _operation_model_string_list(
            repaired.get("references"),
            path=f"{item_path}.references",
            removed_paths=removed_paths,
            candidate_keys=("name", "className", "class_name", "ref"),
        )
        repaired_items.append(repaired)
    return repaired_items


def _ai_draft_pack_quality_gates_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> dict[str, Any]:
    repaired = _aliased_mapping_without_extra_fields(
        value if isinstance(value, dict) else {},
        allowed_keys=_AI_DRAFT_PACK_QUALITY_GATE_KEYS,
        aliases=_AI_DRAFT_PACK_QUALITY_GATE_ALIASES,
        path=path,
        removed_paths=removed_paths,
    )
    for key in (
        "requiredDtoClasses",
        "requiredServiceMethods",
        "requiredMapperMethods",
        "blockerPatterns",
    ):
        repaired[key] = _operation_model_string_list(
            repaired.get(key),
            path=f"{path}.{key}",
            removed_paths=removed_paths,
            candidate_keys=("name", "className", "class_name", "method", "id", "pattern"),
        )
    repaired["requiredReviewMarkers"] = _operation_model_string_list(
        repaired.get("requiredReviewMarkers"),
        path=f"{path}.requiredReviewMarkers",
        removed_paths=removed_paths,
        candidate_keys=("code", "marker", "name", "message", "summary"),
    )
    return repaired


def _operation_model_without_schema_drift(output_text: str) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return {}, []
    if not isinstance(payload, dict):
        return {}, []

    removed_paths: list[str] = []
    payload = _operation_model_payload_from_wrapper(payload, removed_paths=removed_paths)
    repaired = _aliased_mapping_without_extra_fields(
        payload,
        allowed_keys=_OPERATION_MODEL_ROOT_KEYS,
        aliases=_OPERATION_MODEL_ROOT_ALIASES,
        path="$",
        removed_paths=removed_paths,
    )
    repaired["operations"] = _operation_items_without_schema_drift(
        repaired.get("operations"),
        path="$.operations",
        removed_paths=removed_paths,
    )
    repaired["statementEvidence"] = _statement_items_without_schema_drift(
        repaired.get("statementEvidence"),
        path="$.statementEvidence",
        removed_paths=removed_paths,
    )
    repaired["dtoBlueprints"] = _dto_items_without_schema_drift(
        repaired.get("dtoBlueprints"),
        path="$.dtoBlueprints",
        removed_paths=removed_paths,
    )
    _repair_operation_model_reference_aliases(repaired, removed_paths=removed_paths)
    repaired["reviewMarkers"] = _operation_model_string_list(
        repaired.get("reviewMarkers"),
        path="$.reviewMarkers",
        removed_paths=removed_paths,
        candidate_keys=("code", "marker", "name", "message", "summary"),
    )
    repaired["evidenceRefs"] = _operation_model_string_list(
        repaired.get("evidenceRefs"),
        path="$.evidenceRefs",
        removed_paths=removed_paths,
        candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
    )
    repaired["assumptions"] = _operation_model_string_list(
        repaired.get("assumptions"),
        path="$.assumptions",
        removed_paths=removed_paths,
        candidate_keys=("summary", "text", "message", "description"),
    )
    return repaired, sorted(set(removed_paths))


def _operation_model_payload_from_wrapper(
    payload: dict[str, Any],
    *,
    removed_paths: list[str],
) -> dict[str, Any]:
    if _looks_like_operation_model_payload(payload):
        return payload
    for key in ("operationModel", "spOperationModel", "structuredOutput", "output", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict) and _looks_like_operation_model_payload(nested):
            removed_paths.append(f"$.{key}")
            return nested
    return payload


def _looks_like_operation_model_payload(payload: Mapping[str, Any]) -> bool:
    keys = set(payload) | {_OPERATION_MODEL_ROOT_ALIASES.get(key, key) for key in payload}
    return bool(keys & {"operations", "statementEvidence", "dtoBlueprints"})


def _operation_items_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    items = _operation_model_value_list(value, path=path, removed_paths=removed_paths)
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        repaired = _aliased_mapping_without_extra_fields(
            raw_item,
            allowed_keys=_OPERATION_MODEL_OPERATION_KEYS,
            aliases=_OPERATION_MODEL_OPERATION_ALIASES,
            path=item_path,
            removed_paths=removed_paths,
        )
        if isinstance(raw_item.get("reviewMarkers"), list):
            risk_markers = list(repaired.get("riskMarkers") or [])
            for marker in raw_item["reviewMarkers"]:
                marker_text = _operation_model_string_value(
                    marker,
                    candidate_keys=("code", "marker", "name", "message", "summary"),
                )
                if marker_text and marker_text not in risk_markers:
                    risk_markers.append(marker_text)
            repaired["riskMarkers"] = risk_markers
        repaired["statementRefs"] = _operation_model_string_list(
            repaired.get("statementRefs"),
            path=f"{item_path}.statementRefs",
            removed_paths=removed_paths,
            candidate_keys=("statementId", "statement_id", "id", "ref"),
        )
        repaired["dtoBlueprintRefs"] = _operation_model_string_list(
            repaired.get("dtoBlueprintRefs"),
            path=f"{item_path}.dtoBlueprintRefs",
            removed_paths=removed_paths,
            candidate_keys=("name", "className", "class_name", "ref"),
        )
        repaired["stateTransitions"] = _operation_model_string_list(
            repaired.get("stateTransitions"),
            path=f"{item_path}.stateTransitions",
            removed_paths=removed_paths,
            candidate_keys=("code", "summary", "text", "message"),
        )
        repaired["riskMarkers"] = _operation_model_string_list(
            repaired.get("riskMarkers"),
            path=f"{item_path}.riskMarkers",
            removed_paths=removed_paths,
            candidate_keys=("code", "marker", "name", "message", "summary"),
        )
        repaired["evidenceRefs"] = _operation_model_string_list(
            repaired.get("evidenceRefs"),
            path=f"{item_path}.evidenceRefs",
            removed_paths=removed_paths,
            candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
        )
        branch_condition = repaired.get("branchCondition")
        repaired["branchCondition"] = _aliased_mapping_without_extra_fields(
            branch_condition if isinstance(branch_condition, dict) else {},
            allowed_keys=_OPERATION_MODEL_BRANCH_KEYS,
            aliases=_OPERATION_MODEL_BRANCH_ALIASES,
            path=f"{item_path}.branchCondition",
            removed_paths=removed_paths,
        )
        repaired["branchCondition"]["variables"] = _operation_model_string_list(
            repaired["branchCondition"].get("variables"),
            path=f"{item_path}.branchCondition.variables",
            removed_paths=removed_paths,
            candidate_keys=("name", "variable", "param", "parameter"),
        )
        repaired["branchCondition"]["evidenceRefs"] = _operation_model_string_list(
            repaired["branchCondition"].get("evidenceRefs"),
            path=f"{item_path}.branchCondition.evidenceRefs",
            removed_paths=removed_paths,
            candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
        )
        repaired_items.append(repaired)
    return repaired_items


def _statement_items_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    items = _operation_model_value_list(value, path=path, removed_paths=removed_paths)
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        repaired_items.append(
            _statement_item_lists_without_schema_drift(
                _aliased_mapping_without_extra_fields(
                    raw_item,
                    allowed_keys=_OPERATION_MODEL_STATEMENT_KEYS,
                    aliases=_OPERATION_MODEL_STATEMENT_ALIASES,
                    path=item_path,
                    removed_paths=removed_paths,
                ),
                path=item_path,
                removed_paths=removed_paths,
            )
        )
    return repaired_items


def _statement_item_lists_without_schema_drift(
    repaired: dict[str, Any],
    *,
    path: str,
    removed_paths: list[str],
) -> dict[str, Any]:
    for key in ("inputs", "outputs", "writes"):
        repaired[key] = _operation_model_string_list(
            repaired.get(key),
            path=f"{path}.{key}",
            removed_paths=removed_paths,
            candidate_keys=("name", "column", "param", "parameter", "field"),
        )
    repaired["reviewMarkers"] = _operation_model_string_list(
        repaired.get("reviewMarkers"),
        path=f"{path}.reviewMarkers",
        removed_paths=removed_paths,
        candidate_keys=("code", "marker", "name", "message", "summary"),
    )
    repaired["evidenceRefs"] = _operation_model_string_list(
        repaired.get("evidenceRefs"),
        path=f"{path}.evidenceRefs",
        removed_paths=removed_paths,
        candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
    )
    return repaired


def _dto_items_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    items = _operation_model_value_list(value, path=path, removed_paths=removed_paths)
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        repaired = _aliased_mapping_without_extra_fields(
            raw_item,
            allowed_keys=_OPERATION_MODEL_DTO_KEYS,
            aliases=_OPERATION_MODEL_DTO_ALIASES,
            path=item_path,
            removed_paths=removed_paths,
        )
        repaired["fields"] = _dto_field_items_without_schema_drift(
            repaired.get("fields"),
            path=f"{item_path}.fields",
            removed_paths=removed_paths,
        )
        repaired["operationIds"] = _operation_model_string_list(
            repaired.get("operationIds"),
            path=f"{item_path}.operationIds",
            removed_paths=removed_paths,
            candidate_keys=("operationId", "operation_id", "id", "ref"),
        )
        repaired["evidenceRefs"] = _operation_model_string_list(
            repaired.get("evidenceRefs"),
            path=f"{item_path}.evidenceRefs",
            removed_paths=removed_paths,
            candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
        )
        repaired["reviewMarkers"] = _operation_model_string_list(
            repaired.get("reviewMarkers"),
            path=f"{item_path}.reviewMarkers",
            removed_paths=removed_paths,
            candidate_keys=("code", "marker", "name", "message", "summary"),
        )
        repaired_items.append(repaired)
    return repaired_items


def _dto_field_items_without_schema_drift(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[dict[str, Any]]:
    items = _operation_model_value_list(value, path=path, removed_paths=removed_paths)
    repaired_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            removed_paths.append(item_path)
            continue
        repaired = _aliased_mapping_without_extra_fields(
            raw_item,
            allowed_keys=_OPERATION_MODEL_DTO_FIELD_KEYS,
            aliases=_OPERATION_MODEL_DTO_FIELD_ALIASES,
            path=item_path,
            removed_paths=removed_paths,
        )
        repaired["evidenceRefs"] = _operation_model_string_list(
            repaired.get("evidenceRefs"),
            path=f"{item_path}.evidenceRefs",
            removed_paths=removed_paths,
            candidate_keys=("id", "ref", "evidenceRef", "evidence_ref", "code"),
        )
        repaired_items.append(repaired)
    return repaired_items


def _operation_model_string_list(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
    candidate_keys: Sequence[str],
) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if not isinstance(value, list):
        removed_paths.append(path)
    repaired: list[str] = []
    for index, item in enumerate(values):
        text = _operation_model_string_value(item, candidate_keys=candidate_keys)
        if text:
            if not isinstance(item, str):
                removed_paths.append(f"{path}[{index}]")
            if text not in repaired:
                repaired.append(text)
            continue
        removed_paths.append(f"{path}[{index}]")
    return repaired


def _operation_model_string_value(
    value: Any,
    *,
    candidate_keys: Sequence[str],
) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        text = _first_string(value, candidate_keys)
        if text:
            return text
        return _provider_optional_text(value)
    return None


def _repair_operation_model_reference_aliases(
    payload: dict[str, Any],
    *,
    removed_paths: list[str],
) -> None:
    statements = [
        item for item in payload.get("statementEvidence", []) if isinstance(item, Mapping)
    ]
    operations = [
        item for item in payload.get("operations", []) if isinstance(item, Mapping)
    ]
    dtos = [item for item in payload.get("dtoBlueprints", []) if isinstance(item, Mapping)]
    statement_aliases = _operation_statement_ref_aliases(statements)
    dto_aliases = _dto_blueprint_ref_aliases(dtos)
    operation_aliases = _operation_id_aliases(operations)
    for index, operation in enumerate(operations):
        operation["statementRefs"] = _mapped_operation_model_refs(
            operation.get("statementRefs"),
            aliases=statement_aliases,
            path=f"$.operations[{index}].statementRefs",
            removed_paths=removed_paths,
        )
        operation["dtoBlueprintRefs"] = _mapped_operation_model_refs(
            operation.get("dtoBlueprintRefs"),
            aliases=dto_aliases,
            path=f"$.operations[{index}].dtoBlueprintRefs",
            removed_paths=removed_paths,
        )
    for index, dto in enumerate(dtos):
        dto["operationIds"] = _mapped_operation_model_refs(
            dto.get("operationIds"),
            aliases=operation_aliases,
            path=f"$.dtoBlueprints[{index}].operationIds",
            removed_paths=removed_paths,
        )


def _dto_blueprint_ref_aliases(dtos: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for dto in dtos:
        name = str(dto.get("name") or "")
        if not name:
            continue
        aliases[name] = name
        aliases[f"dto.{name}"] = name
        aliases[f"{name}.java"] = name
        aliases[f"dto.{name}.java"] = name
        aliases[name.lower()] = name
        aliases[f"dto.{name.lower()}"] = name
    return aliases


def _operation_id_aliases(operations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for operation in operations:
        operation_id = str(operation.get("operationId") or "")
        if not operation_id:
            continue
        aliases[operation_id] = operation_id
        aliases[operation_id.lower()] = operation_id
        crud_flag = str(operation.get("crudFlag") or "")
        if crud_flag:
            aliases[crud_flag] = operation_id
            aliases[crud_flag.lower()] = operation_id
            aliases[f"crud_{crud_flag.lower()}"] = operation_id
            aliases[f"op.crud_{crud_flag.lower()}"] = operation_id
    return aliases


def _mapped_operation_model_refs(
    refs: Any,
    *,
    aliases: Mapping[str, str],
    path: str,
    removed_paths: list[str],
) -> list[str]:
    values = refs if isinstance(refs, list) else []
    repaired: list[str] = []
    for index, ref in enumerate(values):
        ref_text = str(ref).strip()
        if not ref_text:
            removed_paths.append(f"{path}[{index}]")
            continue
        mapped_ref = aliases.get(ref_text, aliases.get(ref_text.lower(), ref_text))
        if mapped_ref != ref_text:
            removed_paths.append(f"{path}[{index}]")
        if mapped_ref not in repaired:
            repaired.append(mapped_ref)
    return repaired


def _operation_model_value_list(
    value: Any,
    *,
    path: str,
    removed_paths: list[str],
) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        removed_paths.append(path)
        return [value]
    if value is not None:
        removed_paths.append(path)
    return []


def _aliased_mapping_without_extra_fields(
    payload: Any,
    *,
    allowed_keys: set[str],
    aliases: Mapping[str, str],
    path: str,
    removed_paths: list[str],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        removed_paths.append(path)
        return {}
    repaired: dict[str, Any] = {}
    for key, value in payload.items():
        canonical_key = aliases.get(key, key)
        if canonical_key not in allowed_keys:
            removed_paths.append(f"{path}.{key}")
            continue
        if canonical_key != key:
            removed_paths.append(f"{path}.{key}")
        if (
            canonical_key in repaired
            and isinstance(repaired[canonical_key], list)
            and isinstance(value, list)
        ):
            repaired[canonical_key].extend(
                item for item in value if item not in repaired[canonical_key]
            )
            continue
        repaired[canonical_key] = value
    return repaired


def _pgpt_json_object_output_text(
    output_text: str,
    *,
    action: str,
) -> tuple[str, list[dict[str, Any]]]:
    payload = _json_object_from_mixed_text(output_text)
    if payload is None:
        raise ValueError("No P-GPT JSON object found.")
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        [
            {
                "component": "pgpt_json_object_adapter",
                "status": "SUCCEEDED",
                "action": action,
            }
        ],
    )


def _json_object_from_mixed_text(output_text: str) -> dict[str, Any] | None:
    candidates = [output_text.strip()]
    candidates.extend(match.group(1).strip() for match in _JSON_FENCE_RE.finditer(output_text))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


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
    candidates.extend(_embedded_json_object_candidates(output_text))
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


def _embedded_json_object_candidates(output_text: str) -> list[str]:
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    for match in re.finditer(r"\{", output_text):
        try:
            value, end_index = decoder.raw_decode(output_text[match.start() :])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        candidates.append(output_text[match.start() : match.start() + end_index])
        if len(candidates) >= 8:
            break
    return candidates


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
