from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import ArtifactType
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from api_app.metadata_gateway import MetadataCollectionResult
from api_app.repositories import ArtifactRecord
from api_app.schemas import SPAnalysisRequest

ROOT = Path(__file__).resolve().parents[2]
P41_FIXTURE_PATH = ROOT / "fixtures" / "eval" / "sp_operation_model_p41_manage_bond_v1.yaml"
P42_FIXTURE_PATH = ROOT / "fixtures" / "eval" / "ai_draft_pack_p42_manage_bond_v1.yaml"

REQUIRED_P42_REVIEW_MARKERS = {
    "CROSS_DB_WRITE_REVIEW_REQUIRED",
    "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
    "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
    "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
}

SANITIZED_MANAGE_BOND_SQL = """
CREATE PROCEDURE PPM.dbo.PCO_GU_ManageBond_PRC
    @CRUDFlag varchar(20),
    @GUBUNFlag varchar(1),
    @ContractNum varchar(10),
    @OrdNum smallint,
    @BondKindCode varchar(3),
    @Sequence smallint,
    @ApprovalYN varchar(1),
    @CurrencyInsureAmt decimal(18,3),
    @UserID varchar(50),
    @SValue varchar(max)
AS
BEGIN
    IF @CRUDFlag = 'R'
    BEGIN
        SELECT CTRT_NO, ORDR_NO, GUAR_TP_CD, GUAR_ST_CD
        FROM PPM.dbo.PCO_GUAR
        WHERE CTRT_NO = @ContractNum AND ORDR_NO = @OrdNum;
    END
    IF @CRUDFlag = 'A'
    BEGIN
        UPDATE PPM.dbo.PCO_GUAR
        SET GUAR_APRV_YN = @ApprovalYN
        WHERE CTRT_NO = @ContractNum;
        UPDATE ERP.dbo.XXEAI_TRX_HEADER_II
        SET DUE_DATE = GETDATE()
        WHERE INVOICE_NUM = @Sequence;
        EXEC PPM.dbo.PCS_PY_SaveInvoicePrepaidReg_PRC @ContractNum, @OrdNum, @UserID;
    END
    IF @CRUDFlag = 'C'
    BEGIN
        INSERT INTO PPM.dbo.PCO_GUAR (CTRT_NO, ORDR_NO, GUAR_TP_CD, GUAR_AMT)
        SELECT @ContractNum, @OrdNum, @BondKindCode, @CurrencyInsureAmt;
    END
    IF @CRUDFlag = 'U'
    BEGIN
        UPDATE PPM.dbo.PCO_GUAR SET GUAR_AMT = @CurrencyInsureAmt WHERE GUAR_SEQ = @Sequence;
    END
    IF @CRUDFlag = 'D'
    BEGIN
        DELETE FROM PPM.dbo.PCO_GUAR WHERE CTRT_NO = @ContractNum AND GUAR_SEQ = @Sequence;
    END
    IF @CRUDFlag = 'VENDOR_U'
    BEGIN
        UPDATE PPM.dbo.PCS_ADVM_PAYRPT SET VNDR_GUAR_NO = @SValue WHERE @GUBUNFlag = 'J';
    END
    IF @CRUDFlag = 'ONLINE_U'
    BEGIN
        UPDATE PPM.dbo.PCS_PAY_CMPD_RPT SET ONLINE_GUAR_NO = @SValue WHERE @GUBUNFlag = 'G';
    END
END
""".strip()


def manage_bond_request(*, use_llm_analysis: bool = True) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        manage_bond_request_payload(use_llm_analysis=use_llm_analysis)
    )


def manage_bond_request_payload(*, use_llm_analysis: bool = True) -> dict[str, Any]:
    return {
        "dbProfileId": "ppm",
        "target": {
            "type": "PROCEDURE",
            "schema": "dbo",
            "name": "PCO_GU_ManageBond_PRC",
        },
        "outputs": ["JAVA_MYBATIS_DRAFT"],
        "options": {
            "includeEvidenceRefs": True,
            "useLlmAnalysis": use_llm_analysis,
            "llmProfileId": "openai_fast_test",
            "allowSpDefinitionToModel": True,
        },
    }


def p41_operation_model_fixture() -> dict[str, Any]:
    return yaml.safe_load(P41_FIXTURE_PATH.read_text(encoding="utf-8"))["operation_model"]


def p42_ai_draft_pack_fixture() -> dict[str, Any]:
    fixture = yaml.safe_load(P42_FIXTURE_PATH.read_text(encoding="utf-8"))
    target = fixture["ai_draft_pack_quality_target"]
    quality_gates = fixture["quality_gates"]
    return {
        "schemaVersion": target["schemaVersion"],
        "contractTarget": target["contractTarget"],
        "targetRef": target["targetRef"],
        "sourcePolicy": target["sourcePolicy"],
        "productionReady": target["productionReady"],
        "files": [_p42_materialized_file(file) for file in target["expectedFiles"]],
        "evidenceRefs": list(target["evidenceRefs"]),
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
        "assumptions": [
            "P42 workflow fixture uses sanitized draft content and productionReady=false."
        ],
    }


def p42_pack_from_persisted_artifacts(
    artifacts: list[ArtifactRecord],
    *,
    expected_pack: dict[str, Any],
) -> dict[str, Any]:
    expected_by_path = {file["path"]: file for file in expected_pack["files"]}
    files: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.type not in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }:
            continue
        path = str(artifact.extra.get("bundleFilePath") or artifact.title)
        expected = expected_by_path[path]
        payload = {
            "artifactType": artifact.type.value,
            "path": path,
            "role": artifact.extra["aiFileRole"],
            "className": expected["className"],
            "content": artifact.content,
            "operationIds": list(artifact.extra["operationIds"]),
            "evidenceRefs": list(artifact.extra["aiEvidenceRefs"]),
            "reviewMarkers": list(artifact.extra.get("reviewMarkers") or []),
        }
        for optional_key in ("dtoRole", "requiredFields", "references"):
            value = artifact.extra.get(optional_key)
            if value is None and optional_key in expected:
                value = deepcopy(expected[optional_key])
            if value is not None:
                payload[optional_key] = value
        files.append(payload)
    return {
        "schemaVersion": expected_pack["schemaVersion"],
        "contractTarget": expected_pack["contractTarget"],
        "targetRef": expected_pack["targetRef"],
        "sourcePolicy": expected_pack["sourcePolicy"],
        "productionReady": expected_pack["productionReady"],
        "files": sorted(files, key=lambda item: item["path"]),
        "evidenceRefs": list(expected_pack["evidenceRefs"]),
        "reviewMarkers": list(expected_pack["reviewMarkers"]),
        "qualityGates": deepcopy(expected_pack["qualityGates"]),
        "assumptions": list(expected_pack.get("assumptions") or []),
    }


def validate_persisted_p42_pack(
    artifacts: list[ArtifactRecord],
    *,
    expected_pack: dict[str, Any],
):
    return validate_ai_java_mybatis_draft_pack_quality(
        p42_pack_from_persisted_artifacts(artifacts, expected_pack=expected_pack)
    )


def _p42_materialized_file(file: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "artifactType": file["artifactType"],
        "path": file["path"],
        "role": file["role"],
        "className": file["className"],
        "content": _p42_materialized_content(file),
        "operationIds": list(file["operationIds"]),
        "evidenceRefs": list(file["evidenceRefs"]),
        "reviewMarkers": list(file.get("reviewMarkers") or []),
    }
    for optional_key in ("dtoRole", "requiredFields", "references"):
        if optional_key in file:
            payload[optional_key] = deepcopy(file[optional_key])
    return payload


def _p42_materialized_content(file: dict[str, Any]) -> str:
    artifact_type = file["artifactType"]
    class_name = file["className"]
    if artifact_type == "DTO_DRAFT":
        fields = "\n".join(f"    private String {field};" for field in file["requiredFields"])
        markers = " ".join(file.get("reviewMarkers") or ["REVIEW_REQUIRED"])
        return f"public class {class_name} {{\n    // {markers} draft DTO.\n{fields}\n}}"
    if artifact_type == "SERVICE_DRAFT":
        return _p42_service_content(file)
    if artifact_type == "MAPPER_INTERFACE":
        return _p42_mapper_interface_content(file)
    if artifact_type == "MAPPER_XML":
        return _p42_mapper_xml_content(file)
    raise AssertionError(f"Unexpected P42 artifact type: {artifact_type}")


def _p42_method_parameter_type(method: str) -> str:
    return {
        "readBond": "ManageBondSearchCriteria",
        "approveAdvanceBond": "ApproveAdvanceBondCommand",
        "approveDefectBond": "ApproveDefectBondCommand",
        "sendFinanceTransfer": "FinanceTransferCommand",
        "createBond": "CreateBondCommand",
        "createRetentionBondBatch": "CreateRetentionBondBatchItem",
        "updateBond": "UpdateBondCommand",
        "deleteBond": "DeleteBondCommand",
        "updateVendorBond": "VendorBondUpdateCommand",
        "updateOnlineBond": "OnlineBondUpdateCommand",
    }[method]


def _p42_service_content(file: dict[str, Any]) -> str:
    methods = []
    for method in file["operationIds"]:
        parameter_type = _p42_method_parameter_type(method)
        if method == "readBond":
            methods.append(
                "    public List<ManageBondSearchRow> "
                "readBond(ManageBondSearchCriteria criteria) { return mapper.readBond(criteria); }"
            )
        else:
            methods.append(
                f"    public int {method}({parameter_type} command) "
                f"{{ return mapper.{method}(command); }}"
            )
    references = " ".join(file["references"])
    return (
        "import java.util.List;\n"
        "public class ManageBondService {\n"
        "    private final ManageBondMapper mapper;\n"
        "    public ManageBondService(ManageBondMapper mapper) { this.mapper = mapper; }\n"
        f"    // REVIEW_REQUIRED draft references: {references}\n"
        f"{chr(10).join(methods)}\n"
        "}"
    )


def _p42_mapper_interface_content(file: dict[str, Any]) -> str:
    methods = []
    for method in file["operationIds"]:
        parameter_type = _p42_method_parameter_type(method)
        if method == "readBond":
            methods.append(
                "    List<ManageBondSearchRow> readBond(ManageBondSearchCriteria criteria);"
            )
        else:
            methods.append(f"    int {method}({parameter_type} command);")
    references = " ".join(file["references"])
    return (
        "import java.util.List;\n"
        "public interface ManageBondMapper {\n"
        f"    // REVIEW_REQUIRED draft references: {references}\n"
        f"{chr(10).join(methods)}\n"
        "}"
    )


def _p42_mapper_xml_content(file: dict[str, Any]) -> str:
    statements = []
    for method in file["operationIds"]:
        parameter_type = _p42_method_parameter_type(method)
        if method == "readBond":
            statements.append(
                '  <select id="readBond" parameterType="ManageBondSearchCriteria" '
                'resultType="ManageBondSearchRow">'
                "/* SQL_SKELETON_REVIEW_REQUIRED */</select>"
            )
        else:
            statements.append(
                f'  <update id="{method}" parameterType="{parameter_type}">'
                "/* SQL_SKELETON_REVIEW_REQUIRED */</update>"
            )
    references = " ".join(file["references"])
    return (
        '<mapper namespace="ManageBondMapper">\n'
        f"  <!-- REVIEW_REQUIRED DTO references: {references} -->\n"
        f"{chr(10).join(statements)}\n"
        "</mapper>"
    )


class ManageBondMetadataGateway:
    def __init__(self, *, definition: str | None = SANITIZED_MANAGE_BOND_SQL) -> None:
        self.definition = definition

    def collect_procedure_metadata(
        self,
        *,
        db_profile_id: str,
        schema: str,
        procedure_name: str,
    ) -> MetadataCollectionResult:
        definition_payload = (
            {
                "definition": self.definition,
                "definitionHash": "sha256:sanitized-manage-bond",
                "hasDefinitionAccess": True,
            }
            if self.definition is not None
            else None
        )
        return MetadataCollectionResult(
            db_profile_id=db_profile_id,
            object_ref="PPM.dbo.PCO_GU_ManageBond_PRC",
            snapshot_id="snapshot-p41-manage-bond",
            collected_at="2026-05-18T00:00:00Z",
            evidence_refs=(
                {
                    "type": "MSSQL_METADATA",
                    "objectRef": "PPM.dbo.PCO_GU_ManageBond_PRC",
                    "locator": "fixture#/p41/manage-bond",
                    "snapshotId": "snapshot-p41-manage-bond",
                },
            ),
            procedure_definition=definition_payload,
            procedure_parameters={
                "parameters": [
                    {"name": "@CRUDFlag", "dataType": "varchar(20)", "hasDefault": False},
                    {"name": "@GUBUNFlag", "dataType": "varchar(1)", "hasDefault": False},
                    {"name": "@ContractNum", "dataType": "varchar(10)", "hasDefault": False},
                    {"name": "@BondKindCode", "dataType": "varchar(3)", "hasDefault": False},
                    {"name": "@SValue", "dataType": "varchar(max)", "hasDefault": True},
                ]
            },
            table_schemas=(),
        )

    def collect_procedure_definition(
        self,
        *,
        db_profile_id: str,
        schema: str,
        procedure_name: str,
        referenced_database: str | None = None,
    ) -> dict[str, object] | None:
        if self.definition is None:
            return None
        return {
            "data": {
                "definition": self.definition,
                "definitionHash": "sha256:sanitized-manage-bond",
                "hasDefinitionAccess": True,
            },
            "evidenceRefs": [],
        }
