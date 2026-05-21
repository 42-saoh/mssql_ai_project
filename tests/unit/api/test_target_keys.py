from __future__ import annotations

from api_app.target_keys import canonical_target_key, target_key_for_ref, target_key_for_target


def test_canonical_target_key_normalizes_parts_and_unknown_database() -> None:
    assert (
        canonical_target_key(
            db_profile_id=" PPM ",
            database=None,
            object_type="PROCEDURE",
            schema="[dbo]",
            name="[GetInspItemsCd]",
        )
        == "mssql:ppm:-:procedure:dbo.getinspitemscd"
    )


def test_target_key_for_target_uses_known_database() -> None:
    assert (
        target_key_for_target(
            "PPM",
            {"type": "Table", "schema": '"dbo"', "name": "`PEX_INSP_ITEMS`"},
            database="MESDB",
        )
        == "mssql:ppm:mesdb:table:dbo.pex_insp_items"
    )


def test_target_key_for_cross_database_dependency_ref() -> None:
    assert (
        target_key_for_ref(
            db_profile_id="master",
            database="OtherDB",
            object_type="Procedure",
            target_ref="[dbo].[usp_CrossDbOrderAudit]",
        )
        == "mssql:master:otherdb:procedure:dbo.usp_crossdborderaudit"
    )


def test_target_key_for_three_part_ref_uses_ref_database_when_not_supplied() -> None:
    assert (
        target_key_for_ref(
            db_profile_id="master",
            object_type="PROCEDURE",
            target_ref="[OtherDB].[dbo].[usp_CrossDbOrderAudit]",
        )
        == "mssql:master:otherdb:procedure:dbo.usp_crossdborderaudit"
    )
