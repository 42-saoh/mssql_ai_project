"use client";

import { useState } from "react";
import { MetadataTableDetailModal } from "@/components/metadata-table-detail-modal";
import { StatusPill } from "@/components/status-pill";
import type {
  MetadataSearchColumnSummary,
  MetadataSearchResponse,
  MetadataSearchResult,
  MetadataSearchTableSummary,
} from "@/lib/api/types";
import { metadataCaveatMessages, splitMetadataBlockers } from "@/lib/display-caveats";

const DESCRIPTION_FALLBACK = "설명 없음";

type TableDetail = MetadataSearchTableSummary & {
  columns: MetadataSearchColumnSummary[];
};

function normalizedDescription(value?: string | null): string | null {
  const text = value?.trim();
  return text ? text : null;
}

function columnNameFromIdentity(result: MetadataSearchResult): string {
  return result.objectIdentity.name.split(".").pop() ?? result.objectIdentity.name;
}

function parentTableNameFromIdentity(result: MetadataSearchResult): string {
  const parts = result.objectIdentity.name.split(".");
  return parts.length > 1 ? parts.slice(0, -1).join(".") : result.objectIdentity.name;
}

function resultTableSummary(result: MetadataSearchResult): MetadataSearchTableSummary | null {
  if (result.table) {
    return result.table;
  }
  if (result.objectIdentity.type === "TABLE") {
    return {
      schema: result.objectIdentity.schema,
      name: result.objectIdentity.name,
      description: result.description,
    };
  }
  if (result.objectIdentity.type === "COLUMN") {
    return {
      schema: result.objectIdentity.schema,
      name: parentTableNameFromIdentity(result),
      description: null,
    };
  }
  return null;
}

function resultColumnSummary(result: MetadataSearchResult): MetadataSearchColumnSummary {
  return (
    result.column ?? {
      name: columnNameFromIdentity(result),
      description: result.description,
      dataType: result.dataType,
    }
  );
}

function withDescription(name: string, description?: string | null): string {
  const text = normalizedDescription(description);
  return text ? `${name} (${text})` : name;
}

export function formatTableDisplayName(result: MetadataSearchResult): string {
  const table = resultTableSummary(result);
  const name = table?.name ?? result.objectIdentity.name;
  return withDescription(name, table?.description ?? result.description);
}

export function formatColumnDisplayName(result: MetadataSearchResult): string {
  const column = resultColumnSummary(result);
  return withDescription(column.name, column.description ?? result.description);
}

export function formatParentTableDisplayName(result: MetadataSearchResult): string {
  const table = resultTableSummary(result);
  if (!table) {
    return DESCRIPTION_FALLBACK;
  }
  return withDescription(table.name, table.description);
}

function displayDescription(value?: string | null): string {
  return normalizedDescription(value) ?? DESCRIPTION_FALLBACK;
}

function typeLabel(result: MetadataSearchResult): string {
  const labels: Record<string, string> = {
    PROCEDURE: "프로시저",
    TABLE: "테이블",
    COLUMN: "칼럼",
    VIEW: "뷰",
    FUNCTION: "함수",
  };
  return labels[result.objectIdentity.type] ?? result.objectIdentity.type;
}

function statusTone(result: MetadataSearchResult): "PASSED" | "WARNING" | "BLOCKER" {
  if (result.blockers.length > 0) {
    return "BLOCKER";
  }
  return result.reviewRequired ? "WARNING" : "PASSED";
}

function statusLabel(result: MetadataSearchResult): string {
  if (result.blockers.length > 0) {
    return "확인 필요";
  }
  return result.reviewRequired ? "근거 보강 필요" : "확인됨";
}

function tableDetailForResult(result: MetadataSearchResult): TableDetail | null {
  const table = resultTableSummary(result);
  if (!table) {
    return null;
  }
  if (result.objectIdentity.type === "COLUMN" && !result.columns?.length) {
    return null;
  }
  return {
    ...table,
    description: table.description ?? result.description,
    columns: result.columns ?? [],
  };
}

function ResultMain({
  result,
  onOpenTable,
}: Readonly<{
  result: MetadataSearchResult;
  onOpenTable: (table: TableDetail) => void;
}>) {
  const detail = tableDetailForResult(result);
  const caveats = metadataCaveatMessages(result.caveats, result.blockers);
  const description = displayDescription(result.description);

  if (result.objectIdentity.type === "TABLE") {
    return (
      <button
        className="metadata-result-row metadata-result-button"
        type="button"
        onClick={() => detail && onOpenTable(detail)}
      >
        <span className="metadata-result-main">
          <span className="eyebrow">{typeLabel(result)}</span>
          <span className="metadata-result-title">{formatTableDisplayName(result)}</span>
          {!normalizedDescription(result.description) ? (
            <span className="metadata-result-description">{DESCRIPTION_FALLBACK}</span>
          ) : null}
        </span>
        <span className="metadata-result-detail">
          <StatusPill value={statusTone(result)} label={statusLabel(result)} />
          {caveats.length > 0 ? <small>{caveats.join(" · ")}</small> : null}
        </span>
      </button>
    );
  }

  if (result.objectIdentity.type === "COLUMN") {
    const parentLabel = formatParentTableDisplayName(result);
    const parentTable = resultTableSummary(result);
    const column = resultColumnSummary(result);
    const hasColumnDescription = Boolean(
      normalizedDescription(column.description ?? result.description),
    );
    const hasParentDescription = Boolean(normalizedDescription(parentTable?.description));
    return (
      <article className="metadata-result-row">
        <div className="metadata-result-main">
          <p className="eyebrow">{typeLabel(result)}</p>
          <h3>{formatColumnDisplayName(result)}</h3>
          {!hasColumnDescription ? (
            <p className="metadata-result-description">{DESCRIPTION_FALLBACK}</p>
          ) : null}
          {detail ? (
            <button
              className="metadata-parent-button"
              type="button"
              onClick={() => onOpenTable(detail)}
            >
              {parentLabel}
            </button>
          ) : (
            <p>{parentLabel}</p>
          )}
          {!hasParentDescription ? (
            <small className="metadata-result-description">{DESCRIPTION_FALLBACK}</small>
          ) : null}
        </div>
        <div className="metadata-result-detail">
          {result.dataType ? <span className="quiet-label">{result.dataType}</span> : null}
          <StatusPill value={statusTone(result)} label={statusLabel(result)} />
          {caveats.length > 0 ? <small>{caveats.join(" · ")}</small> : null}
        </div>
      </article>
    );
  }

  return (
    <article className="metadata-result-row">
      <div className="metadata-result-main">
        <p className="eyebrow">{typeLabel(result)}</p>
        <h3>{result.objectIdentity.name}</h3>
        <p>{description}</p>
      </div>
      <div className="metadata-result-detail">
        <StatusPill value={statusTone(result)} label={statusLabel(result)} />
        {caveats.length > 0 ? <small>{caveats.join(" · ")}</small> : null}
      </div>
    </article>
  );
}

export function MetadataSearchResults({
  response,
}: Readonly<{
  response: MetadataSearchResponse;
}>) {
  const [selectedTable, setSelectedTable] = useState<TableDetail | null>(null);
  const { caveatBlockers, hardBlockers } = splitMetadataBlockers(response.blockers);
  const responseCaveats = metadataCaveatMessages(response.caveats, caveatBlockers);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Search results</p>
          <h2>{response.query}</h2>
        </div>
        <StatusPill
          value={response.reviewRequired ? "WARNING" : "PASSED"}
          label={response.reviewRequired ? "근거 보강 필요" : "확인됨"}
        />
      </div>

      <dl className="metric-grid">
        <div>
          <dt>Results</dt>
          <dd>{response.results.length}</dd>
        </div>
        <div>
          <dt>Object types</dt>
          <dd>{response.objectTypes.join(", ")}</dd>
        </div>
      </dl>

      {hardBlockers.length > 0 ? (
        <div className="blocker-list">
          {hardBlockers.map((blocker) => (
            <article className="blocker-row" key={blocker.code}>
              <strong>검색 제한</strong>
              <span>{blocker.message}</span>
            </article>
          ))}
        </div>
      ) : null}

      {responseCaveats.length > 0 ? (
        <div className="callout">
          <strong>상태 안내</strong>
          <ul>
            {responseCaveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="metadata-result-list">
        {response.results.map((result) => (
          <ResultMain
            key={`${result.objectIdentity.type}-${result.objectIdentity.schema}-${result.objectIdentity.name}`}
            result={result}
            onOpenTable={setSelectedTable}
          />
        ))}
      </div>

      {selectedTable ? (
        <MetadataTableDetailModal
          table={selectedTable}
          columns={selectedTable.columns}
          onClose={() => setSelectedTable(null)}
        />
      ) : null}
    </section>
  );
}
