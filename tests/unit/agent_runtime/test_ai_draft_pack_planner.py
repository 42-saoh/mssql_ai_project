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
    build_ai_java_mybatis_draft_pack_run,
)
from ai_agent_runtime.gateway import ModelGatewayError, OpenAIModelGateway, model_profile_from_env
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
    assert prompt_payload["draftPackEvidenceBundle"]["version"] == (
        "DraftPackEvidenceBundle.v0.1"
    )
    assert prompt_payload["operationCoverageMatrix"]
    assert prompt_payload["dtoResponsibilityMatrix"]
    assert prompt_payload["reviewMarkerContract"]["requiredMarkers"]
    assert prompt_payload["mapperCoverageContract"]["requiredMapperMethods"]
    assert prompt_payload["filePolicy"]["mustSplitDtoFiles"] is True
    assert prompt_payload["filePolicy"]["genericCoverageFirst"] is True
    assert prompt_payload["filePolicy"]["benchmarkNamesAreNotAnswerKeys"] is True
    assert prompt_payload["filePolicy"]["nonDtoAggregatePolicy"]["exactFiles"]
    assert "aggregate files" in prompt_payload["filePolicy"]["nonDtoAggregatePolicy"]["rule"]
    assert prompt_payload["filePolicy"]["methodCoveragePolicy"]["requiredServiceMethods"]
    assert prompt_payload["evidenceRefContract"]["allowedFactIds"]
    assert "CREATE PROCEDURE" not in prompt.user_prompt
    assert "raw_guide_body" not in prompt.user_prompt
    assert "raw_prompt" not in prompt.user_prompt
    assert "REVIEW_REQUIRED" in prompt.system_prompt
    assert prompt.metadata["expectedFileCount"] == 14
    assert prompt.metadata["evidenceBundleVersion"] == "DraftPackEvidenceBundle.v0.1"


def test_ai_draft_pack_model_profile_uses_high_quality_override(monkeypatch: Any) -> None:
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5")
    monkeypatch.setenv("OPENAI_MODEL_AI_DRAFT_PACK", "gpt-5.5")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_AI_DRAFT_PACK", "high")

    profile = model_profile_from_env("openai_ai_draft_pack")

    assert profile.profile_id == "openai_ai_draft_pack"
    assert profile.model == "gpt-5.5"
    assert profile.registry_ref == "model:openai_ai_draft_pack@gpt-5.5@0.1.0"
    assert profile.reasoning_effort == "high"


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


def test_ai_draft_pack_run_repairs_invalid_structured_output_once() -> None:
    payload = _valid_pack()

    class RepairingGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__(ai_draft_pack_by_target_ref={payload["targetRef"]: payload})
            self.calls = 0

        def draft_ai_java_mybatis_pack(self, *, prompt, profile):
            self.calls += 1
            if self.calls == 1:
                raise ModelGatewayError(
                    "OpenAI response did not match the required structured output schema.",
                    code="OPENAI_AI_DRAFT_PACK_INVALID",
                )
            assert prompt.metadata["stage"] == "repair"
            return super().draft_ai_java_mybatis_pack(prompt=prompt, profile=profile)

    gateway = RepairingGateway()

    run = build_ai_java_mybatis_draft_pack_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_fixture()["ai_draft_pack_quality_target"]["expectedFiles"],
        quality_gates=payload["qualityGates"],
        model_gateway=gateway,
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    assert gateway.calls == 2
    assert run.structured_output["productionReady"] is False
    assert run.model_invocation.component_invocations[-1]["component"] == (
        "ai_draft_pack_repair_stage"
    )
    assert run.model_invocation.component_invocations[-1]["failureStage"] == (
        "model_gateway_structured_output"
    )
    assert "OpenAI response" not in str(run.to_storage_dict())


def test_ai_draft_pack_run_preserves_deterministic_quality_gates() -> None:
    payload = _valid_pack()
    provider_payload = deepcopy(payload)
    provider_payload["qualityGates"]["requiredDtoClasses"] = ["ManageBondSearchCriteria"]
    gateway = FakeModelGateway(
        ai_draft_pack_by_target_ref={payload["targetRef"]: provider_payload}
    )

    run = build_ai_java_mybatis_draft_pack_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_fixture()["ai_draft_pack_quality_target"]["expectedFiles"],
        quality_gates=payload["qualityGates"],
        model_gateway=gateway,
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    assert run.structured_output["qualityGates"] == payload["qualityGates"]
    assert run.model_invocation.structured_output["qualityGates"] == payload["qualityGates"]


def test_ai_draft_pack_run_preserves_generic_expected_dto_references() -> None:
    quality_gates = {
        "requiredDtoClasses": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
        "requiredServiceMethods": ["readSynthetic", "updateSynthetic"],
        "requiredMapperMethods": ["readSynthetic", "updateSynthetic"],
        "requiredReviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
        "blockerPatterns": [],
        "blankContentIsBlocker": True,
        "dtoCollapseIsBlocker": True,
        "fallbackSkeletonPersistenceAllowedOnFailure": False,
    }
    expected_inventory = [
        {
            "artifactType": "DTO_DRAFT",
            "path": "dto/SyntheticSearchCriteria.java",
            "role": "QUERY_DTO",
            "className": "SyntheticSearchCriteria",
            "operationIds": ["readSynthetic"],
            "evidenceRefs": ["ev.synthetic.read"],
        },
        {
            "artifactType": "DTO_DRAFT",
            "path": "dto/SyntheticUpdateCommand.java",
            "role": "COMMAND_DTO",
            "className": "SyntheticUpdateCommand",
            "operationIds": ["updateSynthetic"],
            "evidenceRefs": ["ev.synthetic.update"],
        },
        {
            "artifactType": "SERVICE_DRAFT",
            "path": "service/SyntheticService.java",
            "role": "SERVICE",
            "className": "SyntheticService",
            "operationIds": ["readSynthetic", "updateSynthetic"],
            "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
            "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
        },
        {
            "artifactType": "MAPPER_INTERFACE",
            "path": "mapper/SyntheticMapper.java",
            "role": "MAPPER_INTERFACE",
            "className": "SyntheticMapper",
            "operationIds": ["readSynthetic", "updateSynthetic"],
            "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
            "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
        },
        {
            "artifactType": "MAPPER_XML",
            "path": "mapper/SyntheticMapper.xml",
            "role": "MAPPER_XML",
            "className": "SyntheticMapperSql",
            "operationIds": ["readSynthetic", "updateSynthetic"],
            "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
            "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
        },
    ]
    provider_payload = {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": "PPM.dbo.SyntheticComplex_PRC",
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": [
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/SyntheticSearchCriteria.java",
                "role": "QUERY_DTO",
                "className": "SyntheticSearchCriteria",
                "content": "public class SyntheticSearchCriteria {}",
                "operationIds": ["readSynthetic"],
                "evidenceRefs": ["ev.synthetic.read"],
            },
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/SyntheticUpdateCommand.java",
                "role": "COMMAND_DTO",
                "className": "SyntheticUpdateCommand",
                "content": "public class SyntheticUpdateCommand {}",
                "operationIds": ["updateSynthetic"],
                "evidenceRefs": ["ev.synthetic.update"],
                "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
            },
            {
                "artifactType": "SERVICE_DRAFT",
                "path": "service/SyntheticService.java",
                "role": "SERVICE",
                "className": "SyntheticService",
                "content": "public class SyntheticService { void readSynthetic() {} }",
                "operationIds": ["readSynthetic", "updateSynthetic"],
                "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
            },
            {
                "artifactType": "MAPPER_INTERFACE",
                "path": "mapper/SyntheticMapper.java",
                "role": "MAPPER_INTERFACE",
                "className": "SyntheticMapper",
                "content": "public interface SyntheticMapper { void updateSynthetic(); }",
                "operationIds": ["readSynthetic", "updateSynthetic"],
                "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
            },
            {
                "artifactType": "MAPPER_XML",
                "path": "mapper/SyntheticMapper.xml",
                "role": "MAPPER_XML",
                "className": "SyntheticMapperSql",
                "content": '<mapper><select id="readSynthetic" /></mapper>',
                "operationIds": ["readSynthetic", "updateSynthetic"],
                "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
            },
        ],
        "evidenceRefs": ["ev.synthetic.read", "ev.synthetic.update"],
        "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
        "qualityGates": quality_gates,
    }
    gateway = FakeModelGateway(
        ai_draft_pack_by_target_ref={provider_payload["targetRef"]: provider_payload}
    )

    run = build_ai_java_mybatis_draft_pack_run(
        target_ref=provider_payload["targetRef"],
        sanitized_draft_context={"targetRef": provider_payload["targetRef"]},
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        model_gateway=gateway,
        profile_id="openai_fast_test",
        allowed_evidence_refs=provider_payload["evidenceRefs"],
    )

    non_dto_files = [
        file
        for file in run.structured_output["files"]
        if file["artifactType"] != "DTO_DRAFT"
    ]
    assert all(
        file["references"] == ["SyntheticSearchCriteria", "SyntheticUpdateCommand"]
        for file in non_dto_files
    )
    assert all("SyntheticSearchCriteria" in file["content"] for file in non_dto_files)
    assert any(
        component["component"] == "ai_draft_pack_reference_guard"
        for component in run.model_invocation.component_invocations
    )


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


def test_pgpt_gateway_accepts_fenced_ai_draft_pack_json(monkeypatch: Any) -> None:
    payload = _valid_pack()
    response = httpx.Response(
        200,
        json={
            "id": "resp_pgpt",
            "output_text": "```json\n" + json.dumps(payload) + "\n```",
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        },
        request=httpx.Request("POST", "https://pgpt.test/responses"),
    )
    captured = _capture_post(monkeypatch, response)
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_RESPONSES_URL", "https://pgpt.test/responses")

    result = OpenAIModelGateway(timeout_seconds=1).draft_ai_java_mybatis_pack(
        prompt=_prompt(payload),
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert captured["url"] == "https://pgpt.test/responses"
    assert result.structured_output["targetRef"] == payload["targetRef"]
    assert result.component_invocations[0]["component"] == "pgpt_json_object_adapter"


def test_pgpt_gateway_repairs_non_object_quality_gates_from_prompt(monkeypatch: Any) -> None:
    payload = _valid_pack()
    provider_payload = deepcopy(payload)
    provider_payload["qualityGates"] = []
    provider_payload["reviewMarkers"] = []
    response = httpx.Response(
        200,
        json={
            "id": "resp_pgpt",
            "output_text": json.dumps(provider_payload),
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        },
        request=httpx.Request("POST", "https://pgpt.test/responses"),
    )
    _capture_post(monkeypatch, response)
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_RESPONSES_URL", "https://pgpt.test/responses")

    result = OpenAIModelGateway(timeout_seconds=1).draft_ai_java_mybatis_pack(
        prompt=_prompt(payload),
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert result.structured_output["qualityGates"] == payload["qualityGates"]
    assert set(payload["qualityGates"]["requiredReviewMarkers"]) <= set(
        result.structured_output["reviewMarkers"]
    )


def test_openai_gateway_normalizes_ai_draft_pack_schema_drift(monkeypatch: Any) -> None:
    payload = _valid_pack()
    provider_payload = deepcopy(payload)
    provider_payload["reviewMarkers"] = [
        {"code": marker, "status": "REVIEW_REQUIRED"}
        for marker in payload["reviewMarkers"]
    ]
    provider_payload["assumptions"] = [
        {"summary": "Provider returned a structured assumption object."}
    ]
    first_file = provider_payload["files"][0]
    first_file["class_name"] = first_file.pop("className")
    first_file["operation_ids"] = [
        {"operationId": operation_id} for operation_id in first_file.pop("operationIds")
    ]
    first_file["evidence_refs"] = [
        {"ref": evidence_ref} for evidence_ref in first_file.pop("evidenceRefs")
    ]
    first_file["review_markers"] = [{"code": "FILE_REVIEW_REQUIRED"}]
    first_file.pop("reviewMarkers", None)
    first_file["required_fields"] = [
        {"name": field} for field in first_file.pop("requiredFields", [])
    ]
    first_file["references"] = [
        {"className": reference} for reference in first_file.get("references", [])
    ]
    first_file["providerOnly"] = "remove me"
    _capture_post(monkeypatch, _json_response(provider_payload))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    result = OpenAIModelGateway(timeout_seconds=1).draft_ai_java_mybatis_pack(
        prompt=_prompt(payload),
        profile=model_profile_from_env("openai_fast_test"),
    )

    normalized_file = result.structured_output["files"][0]
    assert result.structured_output["reviewMarkers"] == payload["reviewMarkers"]
    assert result.structured_output["assumptions"] == [
        "Provider returned a structured assumption object."
    ]
    assert normalized_file["className"] == payload["files"][0]["className"]
    assert normalized_file["operationIds"] == payload["files"][0]["operationIds"]
    assert normalized_file["evidenceRefs"] == payload["files"][0]["evidenceRefs"]
    assert normalized_file["reviewMarkers"] == ["FILE_REVIEW_REQUIRED"]
    assert result.component_invocations[-1]["action"] == (
        "normalized_ai_java_mybatis_draft_pack"
    )
    removed_paths = result.component_invocations[-1]["removedFieldPaths"]
    assert "$.files[0].providerOnly" in removed_paths


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
