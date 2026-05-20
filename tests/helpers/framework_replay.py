from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ai_agent_domain import ArtifactType
from ai_agent_generation import GenerationContext

SYNTHETIC_MODEL_PACKAGE = "com.pec.synthetic.workflow.draft.model"
SYNTHETIC_SERVICE_PACKAGE = "com.pec.synthetic.workflow.draft.service"
SYNTHETIC_MAPPER_PACKAGE = "com.pec.synthetic.workflow.draft.mapper"


def synthetic_generation_context() -> GenerationContext:
    target_ref = "dbo.usp_SyntheticComplexOrder_PRC"
    operation_model = {
        "schemaVersion": "SpOperationModel.v0.1",
        "targetRef": target_ref,
        "operations": [
            {
                "operationId": "op.syntheticOrderSearch",
                "statementRefs": ["stmt.synthetic.s001"],
                "dtoBlueprintRefs": [
                    "SyntheticOrderSearchCriteria",
                    "SyntheticOrderSearchRow",
                ],
            },
            {
                "operationId": "op.approveSyntheticOrder",
                "statementRefs": ["stmt.synthetic.s002"],
                "dtoBlueprintRefs": ["ApproveSyntheticOrderCommand"],
            },
            {
                "operationId": "op.syncSyntheticOrderAudit",
                "statementRefs": ["stmt.synthetic.s003"],
                "dtoBlueprintRefs": ["SyntheticOrderAuditCallRequest"],
            },
        ],
        "statementEvidence": [
            {
                "statementId": "stmt.synthetic.s001",
                "operation": "SELECT",
                "phase": "synthetic order search",
                "evidenceRefs": ["fixture.synthetic.s001"],
            },
            {
                "statementId": "stmt.synthetic.s002",
                "operation": "UPDATE",
                "phase": "approve synthetic order",
                "evidenceRefs": ["fixture.synthetic.s002"],
            },
            {
                "statementId": "stmt.synthetic.s003",
                "operation": "EXECUTE",
                "phase": "sync synthetic order audit",
                "evidenceRefs": ["fixture.synthetic.s003"],
            },
        ],
        "dtoBlueprints": [
            dto_blueprint(
                "SyntheticOrderSearchCriteria",
                "QUERY",
                ["op.syntheticOrderSearch"],
                ["ContractNum", "StatusCode"],
                ["fixture.synthetic.s001"],
            ),
            dto_blueprint(
                "SyntheticOrderSearchRow",
                "RESULT",
                ["op.syntheticOrderSearch"],
                ["ContractNum", "OrderStatus"],
                ["fixture.synthetic.s001"],
            ),
            dto_blueprint(
                "ApproveSyntheticOrderCommand",
                "COMMAND",
                ["op.approveSyntheticOrder"],
                ["ContractNum", "ApprovalYN"],
                ["fixture.synthetic.s002"],
                ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
            ),
            dto_blueprint(
                "SyntheticOrderAuditCallRequest",
                "CALL_REQUEST",
                ["op.syncSyntheticOrderAudit"],
                ["ContractNum", "AuditUserId"],
                ["fixture.synthetic.s003"],
                ["CALLED_PROCEDURE_IO_REVIEW_REQUIRED"],
            ),
        ],
        "reviewMarkers": [
            "CROSS_DB_WRITE_REVIEW_REQUIRED",
            "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
            "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
            "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
        ],
    }
    return GenerationContext.from_mapping(
        {
            "sampleId": "framework-replay-synthetic-complex-sp",
            "request": {
                "systemCode": "synthetic",
                "businessCodeLv1": "workflow",
                "businessCodeLv2": "draft",
                "entityName": "SyntheticOrder",
                "resourceName": "synthetic-order",
                "spName": target_ref,
                "operationModel": operation_model,
            },
        }
    )


def dto_blueprint(
    name: str,
    role: str,
    operation_ids: list[str],
    fields: list[str],
    evidence_refs: list[str],
    review_markers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "operationIds": operation_ids,
        "fields": [{"name": field} for field in fields],
        "evidenceRefs": evidence_refs,
        "reviewMarkers": list(review_markers or []),
    }


def pack_from_inventory(
    *,
    target_ref: str,
    expected_inventory: list[dict[str, Any]],
    quality_gates: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": [materialized_file(file) for file in expected_inventory],
        "evidenceRefs": _inventory_evidence_refs(expected_inventory),
        "reviewMarkers": list(quality_gates["requiredReviewMarkers"]),
        "qualityGates": deepcopy(quality_gates),
        "assumptions": ["Framework replay fixture uses sanitized fake adapter output only."],
    }


def materialized_file(file: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "artifactType": file["artifactType"],
        "path": file["path"],
        "role": file["role"],
        "className": file["className"],
        "content": materialized_content(file),
        "operationIds": list(file["operationIds"]),
        "evidenceRefs": list(file["evidenceRefs"]),
        "reviewMarkers": list(file.get("reviewMarkers") or []),
    }
    for key in ("dtoRole", "requiredFields", "references"):
        if key in file:
            payload[key] = deepcopy(file[key])
    return payload


def materialized_content(file: dict[str, Any]) -> str:
    artifact_type = file["artifactType"]
    class_name = file["className"]
    operation_ids = list(file.get("operationIds", []))
    if artifact_type == ArtifactType.DTO_DRAFT.value:
        fields = list(file.get("requiredFields", []))
        fields = "\n".join(
            f"    private String {field};" for field in fields
        )
        accessors = "\n\n".join(
            _string_accessors(field) for field in file.get("requiredFields", [])
        )
        return (
            f"package {SYNTHETIC_MODEL_PACKAGE};\n\n"
            f"public class {class_name} {{\n"
            "    // REVIEW_REQUIRED draft DTO backed by sanitized evidence.\n"
            f"{fields}\n\n"
            f"{accessors}\n"
            "}"
        )
    references = " ".join(file.get("references") or ())
    if artifact_type == ArtifactType.SERVICE_DRAFT.value:
        methods = "\n".join(_service_method(operation_id) for operation_id in operation_ids)
        return (
            f"package {SYNTHETIC_SERVICE_PACKAGE};\n\n"
            f"import {SYNTHETIC_MAPPER_PACKAGE}.SyntheticOrderMapper;\n"
            f"import {SYNTHETIC_MODEL_PACKAGE}.*;\n"
            "import java.util.List;\n"
            "import java.util.Objects;\n\n"
            f"public class {class_name} {{\n"
            "    private final SyntheticOrderMapper mapper;\n"
            f"    public {class_name}(SyntheticOrderMapper mapper) "
            "{ this.mapper = mapper; }\n"
            f"    // REVIEW_REQUIRED DTO references: {references}\n"
            f"{methods}\n"
            "}"
        )
    if artifact_type == ArtifactType.MAPPER_INTERFACE.value:
        methods = "\n".join(
            _mapper_interface_method(operation_id) for operation_id in operation_ids
        )
        return (
            f"package {SYNTHETIC_MAPPER_PACKAGE};\n\n"
            f"import {SYNTHETIC_MODEL_PACKAGE}.*;\n"
            "import java.util.List;\n\n"
            f"public interface {class_name} {{\n"
            f"    // REVIEW_REQUIRED DTO references: {references}\n"
            f"{methods}\n"
            "}"
        )
    statements = "\n".join(_mapper_xml_statement(operation_id) for operation_id in operation_ids)
    return (
        f'<mapper namespace="{SYNTHETIC_MAPPER_PACKAGE}.SyntheticOrderMapper">\n'
        f"  <!-- REVIEW_REQUIRED DTO references: {references} -->\n"
        f'  <resultMap id="SyntheticOrderSearchRowMap" type="{_dto_fqcn("SyntheticOrderSearchRow")}">\n'
        '    <result column="CONTRACT_NUM" property="ContractNum"/>\n'
        '    <result column="ORDER_STATUS" property="OrderStatus"/>\n'
        "  </resultMap>\n"
        f"{statements}\n"
        "</mapper>"
    )


def _string_accessors(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public String get{suffix}() {{\n"
        f"        return {field};\n"
        "    }\n\n"
        f"    public void set{suffix}(String {field}) {{\n"
        f"        this.{field} = {field};\n"
        "    }"
    )


def _dto_fqcn(class_name: str) -> str:
    return f"{SYNTHETIC_MODEL_PACKAGE}.{class_name}"


def _service_method(operation_id: str) -> str:
    if operation_id == "syntheticOrderSearch":
        return (
            "    public List<SyntheticOrderSearchRow> "
            "syntheticOrderSearch(SyntheticOrderSearchCriteria criteria) {\n"
            '        Objects.requireNonNull(criteria, "criteria");\n'
            "        return mapper.syntheticOrderSearch(criteria);\n"
            "    }"
        )
    parameter_type = _operation_parameter_type(operation_id)
    return (
        f"    public int {operation_id}({parameter_type} command) {{\n"
        '        Objects.requireNonNull(command, "command");\n'
        f"        int affectedRows = mapper.{operation_id}(command);\n"
        "        return affectedRows;\n"
        "    }"
    )


def _mapper_interface_method(operation_id: str) -> str:
    if operation_id == "syntheticOrderSearch":
        return (
            "    List<SyntheticOrderSearchRow> "
            "syntheticOrderSearch(SyntheticOrderSearchCriteria criteria);"
        )
    return f"    int {operation_id}({_operation_parameter_type(operation_id)} command);"


def _mapper_xml_statement(operation_id: str) -> str:
    if operation_id == "syntheticOrderSearch":
        return (
            f'  <select id="syntheticOrderSearch" parameterType="{_dto_fqcn("SyntheticOrderSearchCriteria")}" '
            'resultMap="SyntheticOrderSearchRowMap">\n'
            "    SELECT CONTRACT_NUM, ORDER_STATUS\n"
            "    FROM dbo.SyntheticOrderEvidence\n"
            "    WHERE CONTRACT_NUM = #{ContractNum} AND STATUS_CODE = #{StatusCode}\n"
            "  </select>"
        )
    parameter_type = _dto_fqcn(_operation_parameter_type(operation_id))
    if operation_id == "syncSyntheticOrderAudit":
        return (
            f'  <update id="syncSyntheticOrderAudit" parameterType="{parameter_type}">\n'
            "    EXEC dbo.usp_SyncSyntheticOrderAudit #{ContractNum}, #{AuditUserId}\n"
            "  </update>"
        )
    return (
        f'  <update id="{operation_id}" parameterType="{parameter_type}">\n'
        "    UPDATE dbo.SyntheticOrderEvidence\n"
        "    SET APPROVAL_YN = #{ApprovalYN}\n"
        "    WHERE CONTRACT_NUM = #{ContractNum}\n"
        "  </update>"
    )


def _operation_parameter_type(operation_id: str) -> str:
    return {
        "approveSyntheticOrder": "ApproveSyntheticOrderCommand",
        "syncSyntheticOrderAudit": "SyntheticOrderAuditCallRequest",
    }[operation_id]


def collapse_to_two_dtos(pack: dict[str, Any]) -> dict[str, Any]:
    collapsed = deepcopy(pack)
    dto_payloads = dto_files(collapsed)[:2]
    non_dto_files = [
        file
        for file in collapsed["files"]
        if file["artifactType"] != ArtifactType.DTO_DRAFT.value
    ]
    kept_dtos = [file["className"] for file in dto_payloads]
    for file in non_dto_files:
        file["references"] = list(kept_dtos)
        file["content"] = materialized_content(file)
    collapsed["files"] = [*dto_payloads, *non_dto_files]
    collapsed["qualityGates"]["requiredDtoClasses"] = list(kept_dtos)
    return collapsed


def assert_no_collapsed_or_fallback_pack(pack: dict[str, Any]) -> None:
    generated_payload = json.dumps(
        {
            "files": pack["files"],
            "reviewMarkers": pack.get("reviewMarkers", []),
            "assumptions": pack.get("assumptions", []),
        },
        ensure_ascii=False,
    )
    class_names = [file["className"] for file in dto_files(pack)]
    assert "OperationModelReviewRequired" not in generated_payload
    assert "ManageBondDTO" not in generated_payload
    assert not any(
        class_name.endswith("DTO") and len(class_names) == 1
        for class_name in class_names
    )
    assert all(str(file.get("content") or "").strip() for file in pack["files"])
    assert len(class_names) > 2
    assert len(class_names) == len(set(class_names))


def assert_no_raw_trace_leakage(serialized: str) -> None:
    lowered = serialized.lower()
    forbidden = (
        "raw_prompt",
        "raw provider response",
        "raw_provider_response",
        "raw_sp_definition",
        "raw guide body",
        "create procedure",
        "row data",
        "procedure execution",
        "generated source apply",
        "deploy generated source",
        "secret",
        "password",
    )
    for marker in forbidden:
        assert marker not in lowered


def dto_files(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        file
        for file in pack["files"]
        if file["artifactType"] == ArtifactType.DTO_DRAFT.value
    ]


def _inventory_evidence_refs(inventory: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in inventory:
        refs.extend(str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip())
    return list(dict.fromkeys(refs))
