from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from ai_agent_analysis.models import (
    EvidenceStatus,
    MetadataEnrichmentCandidate,
    ObjectReference,
    ObjectType,
)


class SchemaSearchQuery(BaseModel):
    logical_name: str | None = Field(default=None, alias="logicalName")
    description: str | None = None
    columns: list[str] = Field(default_factory=list)


class SchemaSearchCandidate(BaseModel):
    schema_name: str = Field(alias="schema")
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.name}"


class SchemaSearchFixture(BaseModel):
    query: SchemaSearchQuery
    expected_candidates: list[SchemaSearchCandidate] = Field(alias="expectedCandidates")
    source_path: str


def load_schema_search_fixture(path: str | Path) -> SchemaSearchFixture:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["source_path"] = str(fixture_path)
    return SchemaSearchFixture.model_validate(payload)


def enrich_table_references_with_schema_search(
    table_references: list[ObjectReference],
    fixture: SchemaSearchFixture,
) -> list[MetadataEnrichmentCandidate]:
    enrichments: list[MetadataEnrichmentCandidate] = []
    for reference in table_references:
        if reference.object_type != ObjectType.TABLE:
            continue
        match = _find_candidate(reference, fixture.expected_candidates)
        if match is None:
            enrichments.append(
                MetadataEnrichmentCandidate(
                    table_full_name=reference.full_name,
                    source_fixture=fixture.source_path,
                    status=EvidenceStatus.REVIEW_REQUIRED,
                    note="No schema-search fixture candidate matched this table reference.",
                )
            )
            continue
        enrichments.append(
            MetadataEnrichmentCandidate(
                table_full_name=reference.full_name,
                candidate_schema=match.schema_name,
                candidate_name=match.name,
                source_fixture=fixture.source_path,
                matched_fields=["schema", "name"],
                note=(
                    "Matched expected schema-search fixture candidate"
                    f" for query logicalName={fixture.query.logical_name!r}."
                ),
            )
        )
    return enrichments


def _find_candidate(
    reference: ObjectReference,
    candidates: list[SchemaSearchCandidate],
) -> SchemaSearchCandidate | None:
    reference_schema = (reference.schema_name or "").lower()
    reference_name = reference.object_name.lower()
    for candidate in candidates:
        if candidate.name.lower() != reference_name:
            continue
        if reference_schema and candidate.schema_name.lower() != reference_schema:
            continue
        return candidate
    return None
