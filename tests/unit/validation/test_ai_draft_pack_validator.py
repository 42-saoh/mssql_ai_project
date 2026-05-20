from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.ai_draft_pack import (
    RULE_ASCII_IDENTIFIER,
    RULE_DTO_FIELD,
    RULE_DTO_INVENTORY,
    RULE_DTO_STRUCTURE,
    RULE_FORBIDDEN_PAYLOAD,
    RULE_MAPPER_CONSISTENCY,
    RULE_MAPPER_METHOD,
    RULE_MAPPER_XML,
    RULE_MAPPER_XML_DB_OPERATION,
    RULE_MAPPER_XML_PLACEHOLDER,
    RULE_MAPPER_XML_TYPE,
    RULE_NON_DTO_AGGREGATE,
    RULE_NON_DTO_REFERENCE,
    RULE_PACKAGE_CONTEXT,
    RULE_REVIEW_MARKER,
    RULE_SCHEMA,
    RULE_SERVICE_FLOW,
)
from ai_agent_validation.models import ValidationStatus
from tests.helpers.p42_manage_bond import (
    P42_MAPPER_PACKAGE,
    P42_MODEL_PACKAGE,
    P42_SERVICE_PACKAGE,
    p42_ai_draft_pack_fixture,
)


def _valid_pack() -> dict[str, Any]:
    return p42_ai_draft_pack_fixture()


def _file(payload: dict[str, Any], class_name: str) -> dict[str, Any]:
    return next(file for file in payload["files"] if file["className"] == class_name)


def _file_by_type(payload: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    return next(file for file in payload["files"] if file["artifactType"] == artifact_type)


def _failed_rule_ids(payload: dict[str, Any]) -> set[str]:
    report = validate_ai_java_mybatis_draft_pack_quality(payload)
    return {check.rule_id for check in report.failed_checks}


def _dto_content(class_name: str, fields: list[str]) -> str:
    declarations = "\n".join(f"    private String {field};" for field in fields)
    accessors = "\n\n".join(_accessors(field) for field in fields)
    return (
        f"package {P42_MODEL_PACKAGE};\n\n"
        f"public class {class_name} {{\n"
        "    // REVIEW_REQUIRED sanitized regression DTO.\n"
        f"{declarations}\n\n"
        f"{accessors}\n"
        "}"
    )


def _accessors(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public String get{suffix}() {{\n"
        f"        return {field};\n"
        "    }\n\n"
        f"    public void set{suffix}(String {field}) {{\n"
        f"        this.{field} = {field};\n"
        "    }"
    )


def _append_dto(
    payload: dict[str, Any],
    *,
    class_name: str,
    operation_ids: list[str],
    required_fields: list[str],
    dto_role: str = "COMMAND",
) -> None:
    source = deepcopy(_file(payload, "DeleteBondCommand"))
    source.update(
        {
            "path": f"dto/{class_name}.java",
            "className": class_name,
            "operationIds": operation_ids,
            "dtoRole": dto_role,
            "requiredFields": required_fields,
            "content": _dto_content(class_name, required_fields),
        }
    )
    payload["files"].append(source)


def test_valid_manage_bond_pack_passes_quality_gate() -> None:
    report = validate_ai_java_mybatis_draft_pack_quality(_valid_pack())

    assert report.status == ValidationStatus.PASSED
    assert report.failed_checks == ()
    assert report.metadata["productionReady"] is False
    assert report.metadata["scores"]["requiredDtoFileCoverage"] == 1.0
    assert report.metadata["scores"]["requiredServiceMethodCoverage"] == 1.0
    assert report.metadata["scores"]["requiredMapperMethodCoverage"] == 1.0
    assert report.metadata["scores"]["requiredReviewMarkerCoverage"] == 1.0


def test_blank_content_and_schema_failure_are_blockers() -> None:
    payload = _valid_pack()
    payload["files"][0]["content"] = "   "

    assert RULE_SCHEMA in _failed_rule_ids(payload)


def test_fallback_skeleton_and_single_dto_collapse_are_blockers() -> None:
    payload = _valid_pack()
    payload["files"][0]["className"] = "OperationModelReviewRequired"

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    original = payload["files"][0]["className"]
    payload["files"][0]["className"] = "ManageBondDTO"
    payload["files"][0]["path"] = "dto/ManageBondDTO.java"
    payload["files"][0]["content"] = payload["files"][0]["content"].replace(
        original,
        "ManageBondDTO",
    )
    payload["qualityGates"]["requiredDtoClasses"] = [
        "ManageBondDTO" if item == original else item
        for item in payload["qualityGates"]["requiredDtoClasses"]
    ]
    for file in payload["files"]:
        if "references" in file:
            file["references"] = [
                "ManageBondDTO" if item == original else item
                for item in file["references"]
            ]
            file["content"] = file["content"].replace(original, "ManageBondDTO")

    assert RULE_FORBIDDEN_PAYLOAD in _failed_rule_ids(payload)


def test_missing_required_dto_is_a_blocker() -> None:
    payload = _valid_pack()
    payload["files"] = [
        file for file in payload["files"] if file["className"] != "OnlineBondUpdateCommand"
    ]

    assert RULE_SCHEMA in _failed_rule_ids(payload)


def test_missing_dto_required_field_fails_content_quality() -> None:
    payload = _valid_pack()
    dto = _file(payload, "CreateBondCommand")
    dto["content"] = dto["content"].replace("    private String currencyInsureAmt;\n", "")

    assert RULE_DTO_FIELD in _failed_rule_ids(payload)


def test_missing_service_dto_reference_fails_content_quality() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(
        "OnlineBondUpdateCommand",
        "OnlineBondCommand",
    )

    assert RULE_NON_DTO_REFERENCE in _failed_rule_ids(payload)


def test_missing_mapper_method_fails_content_quality() -> None:
    payload = _valid_pack()
    mapper = _file_by_type(payload, "MAPPER_INTERFACE")
    mapper["content"] = mapper["content"].replace(
        "    int updateOnlineBond(OnlineBondUpdateCommand command);\n",
        "",
    )

    failed = _failed_rule_ids(payload)

    assert RULE_MAPPER_METHOD in failed
    assert RULE_MAPPER_CONSISTENCY in failed


def test_invalid_mapper_xml_fails_static_xml_quality() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = "<mapper><select id='readBond'></mapper>"

    assert RULE_MAPPER_XML in _failed_rule_ids(payload)


def test_p50_invalid_java_identifiers_fail_content_quality() -> None:
    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    invalid_class_name = "9ManageBondSearchCriteria"
    dto["className"] = invalid_class_name
    dto["content"] = dto["content"].replace("ManageBondSearchCriteria", invalid_class_name)
    payload["qualityGates"]["requiredDtoClasses"] = [
        invalid_class_name if item == "ManageBondSearchCriteria" else item
        for item in payload["qualityGates"]["requiredDtoClasses"]
    ]
    for file in payload["files"]:
        if "references" in file:
            file["references"] = [
                invalid_class_name if item == "ManageBondSearchCriteria" else item
                for item in file["references"]
            ]
        file["content"] = file["content"].replace(
            "ManageBondSearchCriteria",
            invalid_class_name,
        )

    assert RULE_ASCII_IDENTIFIER in _failed_rule_ids(payload)


def test_p50_placeholder_java_packages_are_blocked() -> None:
    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    dto["content"] = dto["content"].replace(P42_MODEL_PACKAGE, "com.example.dto")

    assert RULE_PACKAGE_CONTEXT in _failed_rule_ids(payload)

    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        f"{P42_MAPPER_PACKAGE}.ManageBondMapper",
        "org.example.mapper.ManageBondMapper",
    )

    assert RULE_PACKAGE_CONTEXT in _failed_rule_ids(payload)

    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(
        f"import {P42_MODEL_PACKAGE}.*;",
        "import example.model.*;",
    )

    assert RULE_PACKAGE_CONTEXT in _failed_rule_ids(payload)


def test_p50_empty_service_body_fails_content_quality() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(
        '        Objects.requireNonNull(command, "command");\n'
        "        int affectedRows = mapper.updateOnlineBond(command);\n"
        "        return affectedRows;\n",
        "",
    )

    assert RULE_SERVICE_FLOW in _failed_rule_ids(payload)


def test_p50_mapper_pass_through_service_is_blocked() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(
        '        Objects.requireNonNull(command, "command");\n'
        "        int affectedRows = mapper.updateOnlineBond(command);\n"
        "        return affectedRows;\n",
        "        return mapper.updateOnlineBond(command);\n",
    )

    assert RULE_SERVICE_FLOW in _failed_rule_ids(payload)


def test_p50_service_call_to_missing_mapper_method_is_blocked() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(
        "mapper.updateOnlineBond(command)",
        "mapper.archiveOnlineBond(command)",
    )

    assert RULE_MAPPER_CONSISTENCY in _failed_rule_ids(payload)


def test_p50_job_68456af0fc_service_and_mapper_xml_regression_is_blocked() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    service["path"] = "service/ManageBondReadQueryService.java"
    service["className"] = "ManageBondReadQueryService"
    service["operationIds"] = ["readBond"]
    service["content"] = (
        f"package {P42_SERVICE_PACKAGE};\n"
        "public class ManageBondReadQueryService {\n"
        "    public void readBond(ManageBondSearchCriteria criteria) {}\n"
        "}"
    )
    mapper_xml["content"] = (
        f'<mapper namespace="{P42_MAPPER_PACKAGE}.ManageBondMapper">\n'
        '  <select id="readBond"></select>\n'
        '  <update id="approveAdvanceBond"></update>\n'
        '  <update id="approveDefectBond"></update>\n'
        '  <update id="sendFinanceTransfer"></update>\n'
        '  <update id="createBond"></update>\n'
        '  <update id="createRetentionBondBatch"></update>\n'
        '  <update id="updateBond"></update>\n'
        '  <update id="deleteBond"></update>\n'
        '  <update id="updateVendorBond"></update>\n'
        '  <update id="updateOnlineBond"></update>\n'
        "</mapper>"
    )

    failed = _failed_rule_ids(payload)

    assert RULE_SERVICE_FLOW in failed
    assert RULE_MAPPER_XML_DB_OPERATION in failed
    assert RULE_NON_DTO_AGGREGATE in failed


def test_p50_mapper_interface_and_xml_must_match() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        'id="updateOnlineBond"',
        'id="updateOnlineBondSql"',
    )

    failed = _failed_rule_ids(payload)

    assert RULE_MAPPER_CONSISTENCY in failed
    assert RULE_MAPPER_XML in failed


def test_p50_mapper_xml_namespace_must_match_interface_fqcn() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        f'namespace="{P42_MAPPER_PACKAGE}.ManageBondMapper"',
        f'namespace="{P42_MAPPER_PACKAGE}.OtherMapper"',
    )

    assert RULE_MAPPER_CONSISTENCY in _failed_rule_ids(payload)


def test_p50_mapper_xml_parameter_and_result_types_must_be_known_dtos() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        f"{P42_MODEL_PACKAGE}.OnlineBondUpdateCommand",
        f"{P42_MODEL_PACKAGE}.MissingCommand",
    )

    assert RULE_MAPPER_XML_TYPE in _failed_rule_ids(payload)


def test_p50_raw_substitution_and_procedure_name_exec_are_blocked() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        "UPDATE PPM.dbo.PCS_PAY_CMPD_RPT",
        "EXEC ${procedureName}",
    )

    assert RULE_MAPPER_XML_PLACEHOLDER in _failed_rule_ids(payload)


def test_p50_placeholder_select_and_review_required_field_are_blocked() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = mapper_xml["content"].replace(
        "SELECT CTRT_NO, ORDR_NO, GUAR_TP_CD, GUAR_ST_CD",
        "SELECT CAST(NULL AS varchar(1)) AS reviewRequiredField",
    )

    assert RULE_MAPPER_XML_PLACEHOLDER in _failed_rule_ids(payload)

    payload = _valid_pack()
    dto = _file(payload, "OnlineBondUpdateCommand")
    dto["requiredFields"] = ["reviewRequiredField"]
    dto["content"] = _dto_content("OnlineBondUpdateCommand", ["reviewRequiredField"])

    assert RULE_DTO_STRUCTURE in _failed_rule_ids(payload)


def test_p50_wrapper_only_original_sp_mapper_xml_fails_content_quality() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = (
        f'<mapper namespace="{P42_MAPPER_PACKAGE}.ManageBondMapper">\n'
        '  <update id="readBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="approveAdvanceBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="approveDefectBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="sendFinanceTransfer">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="createBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="createRetentionBondBatch">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="updateBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="deleteBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="updateVendorBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        '  <update id="updateOnlineBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</update>\n'
        "</mapper>"
    )

    assert RULE_MAPPER_XML_DB_OPERATION in _failed_rule_ids(payload)


def test_p50_shallow_six_file_pack_fails_content_quality() -> None:
    payload = _valid_pack()
    payload["files"] = [
        file
        for file in payload["files"]
        if file["artifactType"] != "DTO_DRAFT"
        or file["className"]
        in {
            "ManageBondSearchCriteria",
            "ManageBondSearchRow",
            "CreateBondCommand",
        }
    ]
    payload["qualityGates"]["requiredDtoClasses"] = [
        "ManageBondSearchCriteria",
        "ManageBondSearchRow",
        "CreateBondCommand",
    ]
    for file in payload["files"]:
        if "references" in file:
            file["references"] = [
                item
                for item in file["references"]
                if item
                in {
                    "ManageBondSearchCriteria",
                    "ManageBondSearchRow",
                    "CreateBondCommand",
                }
            ]
    payload["files"][-1]["content"] = (
        f'<mapper namespace="{P42_MAPPER_PACKAGE}.ManageBondMapper">\n'
        '  <select id="readBond">EXEC dbo.PCO_GU_ManageBond_PRC #{crudFlag}</select>\n'
        '  <update id="createBond"></update>\n'
        "</mapper>"
    )

    failed = _failed_rule_ids(payload)

    assert RULE_MAPPER_XML_DB_OPERATION in failed
    assert RULE_MAPPER_XML in failed


def test_p50_job_b75885a986_fragmented_dto_inventory_is_blocked() -> None:
    payload = _valid_pack()
    for index in range(1, 22):
        _append_dto(
            payload,
            class_name=f"ManageBondProcess{index:03d}",
            operation_ids=[f"processFragment{index}"],
            required_fields=[f"fragmentField{index}"],
        )

    assert RULE_DTO_INVENTORY in _failed_rule_ids(payload)


def test_p50_duplicate_same_operation_same_role_dtos_are_blocked() -> None:
    payload = _valid_pack()
    _append_dto(
        payload,
        class_name="DeleteBondDuplicateCommand",
        operation_ids=["deleteBond"],
        required_fields=["bondKindCode", "contractNum", "ordNum", "sequence"],
    )

    assert RULE_DTO_INVENTORY in _failed_rule_ids(payload)


def test_forbidden_payload_markers_fail_quality_gate() -> None:
    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    dto["content"] = f"{dto['content']}\n// CREATE PROCEDURE dbo.PCO_GU_ManageBond_PRC"

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    dto["content"] = f"{dto['content']}\n// mark this artifact as production ready"

    assert RULE_FORBIDDEN_PAYLOAD in _failed_rule_ids(payload)

    forbidden_cases = [
        "sample rows are included here",
        "execute stored procedure before using this mapper",
        "deployed to production after generated source apply",
    ]
    for forbidden in forbidden_cases:
        payload = _valid_pack()
        dto = _file(payload, "ManageBondSearchCriteria")
        dto["content"] = f"{dto['content']}\n// {forbidden}"

        assert _failed_rule_ids(payload) & {RULE_SCHEMA, RULE_FORBIDDEN_PAYLOAD}


def test_required_review_marker_removal_fails_quality_gate() -> None:
    payload = _valid_pack()
    payload["reviewMarkers"] = []
    for file in payload["files"]:
        file["reviewMarkers"] = []

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    payload["qualityGates"]["requiredReviewMarkers"] = []
    payload["reviewMarkers"] = [
        marker
        for marker in payload["reviewMarkers"]
        if marker != "TRANSACTION_BOUNDARY_REVIEW_REQUIRED"
    ]

    assert RULE_REVIEW_MARKER in _failed_rule_ids(payload)
