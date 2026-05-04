from __future__ import annotations

from api_app.metadata_gateway import McpMetadataGateway


def test_mcp_metadata_gateway_collects_fixture_metadata_through_registry() -> None:
    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="master",
        schema="dbo",
        procedure_name="usp_GetOrderSummary",
    )

    assert metadata.status == "COLLECTED"
    assert metadata.snapshot_id == "mcp-fixture-snapshot-0001"
    assert metadata.primary_table is not None
    assert metadata.primary_table["tableName"] == "TB_ORDER"
    assert metadata.procedure_parameters is not None
    assert metadata.procedure_parameters["parameters"][0]["name"] == "@OrderId"
    assert metadata.evidence_refs


def test_mcp_metadata_gateway_returns_review_required_fallback_for_missing_fixture() -> None:
    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="master",
        schema="dbo",
        procedure_name="usp_NotInFixture",
    )

    assert metadata.status == "REVIEW_REQUIRED"
    assert metadata.snapshot_id is None
    assert metadata.errors
    assert metadata.evidence_refs == (
        {
            "type": "USER_INPUT",
            "objectRef": "dbo.usp_NotInFixture",
            "locator": "request.target",
        },
    )
