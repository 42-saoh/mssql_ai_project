from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import yaml
from ai_agent_runtime import (
    AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
    FakeModelGateway,
    ModelProfile,
)
from ai_agent_runtime.gateway import OpenAIModelGateway, model_profile_from_env
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt

FIXTURE_PATH = Path("fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml")


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))


def _valid_pack() -> dict[str, Any]:
    fixture = _fixture()
    target = fixture["ai_draft_pack_quality_target"]
    quality_gates = fixture["quality_gates"]
    return {
        "schemaVersion": target["schemaVersion"],
        "contractTarget": target["contractTarget"],
        "targetRef": target["targetRef"],
        "sourcePolicy": target["sourcePolicy"],
        "productionReady": target["productionReady"],
        "files": [_file_with_content(file) for file in target["expectedFiles"]],
        "evidenceRefs": target["evidenceRefs"],
        "reviewMarkers": list(target["reviewMarkers"]),
        "qualityGates": {
            "requiredDtoClasses": list(quality_gates["required_dto_classes"]),
            "requiredServiceMethods": list(quality_gates["required_service_methods"]),
            "requiredMapperMethods": list(quality_gates["required_mapper_methods"]),
            "requiredReviewMarkers": list(target["reviewMarkers"]),
            "blockerPatterns": list(quality_gates["blocker_patterns"]),
            "blankContentIsBlocker": bool(quality_gates["blank_content_is_blocker"]),
            "dtoCollapseIsBlocker": bool(quality_gates["dto_collapse_is_blocker"]),
            "fallbackSkeletonPersistenceAllowedOnFailure": bool(
                quality_gates["fallback_skeleton_persistence_allowed_on_failure"]
            ),
        },
        "assumptions": ["P42B fixture pack is draft-only and productionReady=false."],
    }


def _file_with_content(file: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "artifactType": file["artifactType"],
        "path": file["path"],
        "role": file["role"],
        "className": file["className"],
        "content": _content_for(file),
        "operationIds": list(file["operationIds"]),
        "evidenceRefs": list(file["evidenceRefs"]),
        "reviewMarkers": list(file.get("reviewMarkers") or []),
    }
    for optional_key in ("dtoRole", "requiredFields", "references"):
        if optional_key in file:
            payload[optional_key] = deepcopy(file[optional_key])
    return payload


def _content_for(file: dict[str, Any]) -> str:
    class_name = file["className"]
    operation_ids = list(file["operationIds"])
    if file["artifactType"] == "MAPPER_XML":
        statements = "\n".join(
            f'  <select id="{operation_id}" parameterType="map" resultType="map" />'
            for operation_id in operation_ids
        )
        return f'<mapper namespace="ManageBondMapper">\n{statements}\n</mapper>'
    methods = "\n".join(f"    void {operation_id}();" for operation_id in operation_ids)
    if file["artifactType"] == "MAPPER_INTERFACE":
        return f"public interface {class_name} {{\n{methods}\n}}"
    return f"public class {class_name} {{\n    // REVIEW_REQUIRED draft.\n{methods}\n}}"


def _allowed_refs(payload: dict[str, Any]) -> list[str]:
    refs = list(payload["evidenceRefs"])
    for file in payload["files"]:
        refs.extend(file["evidenceRefs"])
    return sorted(set(refs))


def _prompt(payload: dict[str, Any]):
    fixture = _fixture()
    return render_ai_java_mybatis_draft_pack_prompt(
        target_ref=payload["targetRef"],
        sanitized_draft_context={
            "targetRef": payload["targetRef"],
            "branchVariables": fixture["guide_quality_facts"]["branch_variables"],
            "reviewRequiredFacts": fixture["guide_quality_facts"]["review_required_facts"],
            "raw_guide_body": "CREATE PROCEDURE should be removed",
            "raw_prompt": "provider prompt should be removed",
        },
        expected_inventory=fixture["ai_draft_pack_quality_target"]["expectedFiles"],
        quality_gates=payload["qualityGates"],
        allowed_evidence_refs=_allowed_refs(payload),
        stage="file_inventory",
    )


def test_ai_draft_pack_prompt_uses_sanitized_staged_contract() -> None:
    payload = _valid_pack()
    prompt = _prompt(payload)
    prompt_payload = json.loads(prompt.user_prompt)

    assert prompt.prompt_version == AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION
    assert prompt.output_schema_version == AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION
    assert prompt_payload["outputContract"]["schemaVersion"] == "AiJavaMyBatisDraftPack.v0.1"
    assert prompt_payload["stagedOutputFlow"] == [
        "file_inventory",
        "file_content",
        "deterministic_validation",
        "repair",
    ]
    assert prompt_payload["filePolicy"]["mustSplitDtoFiles"] is True
    assert prompt_payload["evidenceRefContract"]["allowedFactIds"]
    assert "CREATE PROCEDURE" not in prompt.user_prompt
    assert "raw_guide_body" not in prompt.user_prompt
    assert "raw_prompt" not in prompt.user_prompt
    assert "REVIEW_REQUIRED" in prompt.system_prompt
    assert prompt.metadata["expectedFileCount"] == 14


def test_fake_gateway_returns_schema_valid_ai_draft_pack() -> None:
    payload = _valid_pack()
    gateway = FakeModelGateway(ai_draft_pack_by_target_ref={payload["targetRef"]: payload})
    profile = ModelProfile(
        profile_id="fake_gateway_fixture",
        model="fake",
        registry_ref="model:fake_gateway_fixture@0.1.0",
        reasoning_effort="none",
    )

    invocation = gateway.draft_ai_java_mybatis_pack(prompt=_prompt(payload), profile=profile)

    assert invocation.output_schema_version == AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION
    assert invocation.structured_output["targetRef"] == payload["targetRef"]
    assert invocation.structured_output["productionReady"] is False
    assert {file["className"] for file in invocation.structured_output["files"]} >= {
        "ManageBondSearchCriteria",
        "ManageBondSearchRow",
        "OnlineBondUpdateCommand",
    }


def test_gateway_storage_summary_keeps_only_hashes_and_structured_output() -> None:
    payload = _valid_pack()
    gateway = FakeModelGateway(ai_draft_pack_by_target_ref={payload["targetRef"]: payload})
    invocation = gateway.draft_ai_java_mybatis_pack(
        prompt=_prompt(payload),
        profile=ModelProfile(
            profile_id="fake_gateway_fixture",
            model="fake",
            registry_ref="model:fake_gateway_fixture@0.1.0",
            reasoning_effort="none",
        ),
    )

    stored = invocation.to_storage_dict()
    stored_text = json.dumps(stored, ensure_ascii=False)

    assert stored["promptHash"]
    assert "system_prompt" not in stored_text
    assert "user_prompt" not in stored_text
    assert "raw_prompt" not in stored_text
    assert "raw_provider_response" not in stored_text
    assert "raw_sp_definition" not in stored_text
    assert "CREATE PROCEDURE" not in stored_text


def test_openai_gateway_uses_responses_json_schema_for_ai_draft_pack(monkeypatch: Any) -> None:
    payload = _valid_pack()
    captured = _capture_post(monkeypatch, _json_response(payload))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    result = OpenAIModelGateway(timeout_seconds=1).draft_ai_java_mybatis_pack(
        prompt=_prompt(payload),
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["text"]["format"]["name"] == "ai_java_mybatis_draft_pack"
    assert captured["json"]["text"]["format"]["strict"] is True
    assert (
        captured["json"]["text"]["format"]["schema"]["properties"]["productionReady"]["const"]
        is False
    )
    assert result.structured_output["targetRef"] == payload["targetRef"]


def _json_response(output: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "resp_test",
            "output_text": json.dumps(output),
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        },
        request=httpx.Request("POST", "https://api.openai.test/v1/responses"),
    )


def _capture_post(monkeypatch: Any, response: httpx.Response) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["json"] = dict(json)
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("ai_agent_runtime.gateway.httpx.post", fake_post)
    return captured
