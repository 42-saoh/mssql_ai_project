"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import type {
  MetadataDesignResult,
  MetadataDesignRunRequest,
  MetadataDesignRunStatus,
  MetadataGeneratedDraft,
  MetadataProfile,
  MetadataStandardizationMapping,
  MetadataTableProposalColumn,
} from "@/lib/api/types";
import {
  DEFAULT_METADATA_PROFILE,
  TABLE_NAME_HINT_PLACEHOLDER,
} from "@/lib/metadata-design/constants";

const DESIGN_TIMEOUT_MS = 120_000;
const DESIGN_POLL_INTERVAL_MS = 1_500;
const NEW_DESIGN_MESSAGE_PLACEHOLDER =
  "고객명, 주소, 주문일이 있는 주문 요청 테이블을 만들어줘.";
const REFINE_CURRENT_MESSAGE_PLACEHOLDER =
  "배송메모를 추가하고, 주문일은 날짜 타입으로 바꿔줘.";

const MSSQL_IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;

interface DesignError {
  code: string;
  message: string;
}

type MetadataDesignConversationMode = NonNullable<
  MetadataDesignRunRequest["options"]
>["conversationMode"];

type EditableMappingField = "proposedName" | "proposedType" | "description";

interface EditableMappingRow {
  id: string;
  inputName: string;
  inputDescription: string;
  proposedName: string;
  proposedType: string;
  nullable: boolean;
  description: string;
  source: MetadataStandardizationMapping["source"];
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

interface MappingValidationError {
  rowId: string;
  field: EditableMappingField;
  message: string;
}

interface PreviewColumn {
  name: string;
  dataType: string;
  nullable: boolean;
  description: string;
  source: MetadataTableProposalColumn["source"];
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

interface RegeneratedPreview {
  rowsSignature: string;
  createTableScriptPreview: string;
  dtoDraft: MetadataGeneratedDraft | null;
}

export function MetadataDesignChat({
  defaultDbProfileId,
  profiles,
}: Readonly<{
  defaultDbProfileId: string;
  profiles: MetadataProfile[];
}>) {
  const fixedProfile = useMemo<MetadataProfile>(
    () =>
      profiles.find((profile) => profile.id === DEFAULT_METADATA_PROFILE) ?? {
        id: DEFAULT_METADATA_PROFILE,
        database: "PPM",
        readOnly: true,
      },
    [profiles],
  );
  const [dbProfileId, setDbProfileId] = useState(DEFAULT_METADATA_PROFILE);
  const [message, setMessage] = useState("");
  const [tableNameHint, setTableNameHint] = useState("");
  const [conversationMode, setConversationMode] =
    useState<MetadataDesignConversationMode>("NEW_DESIGN");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [runs, setRuns] = useState<MetadataDesignRunStatus[]>([]);
  const [run, setRun] = useState<MetadataDesignRunStatus | null>(null);
  const [error, setError] = useState<DesignError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const messagePlaceholder =
    conversationMode === "REFINE_CURRENT"
      ? REFINE_CURRENT_MESSAGE_PLACEHOLDER
      : NEW_DESIGN_MESSAGE_PLACEHOLDER;
  const canSubmit = !isLoading && message.trim().length > 0;

  const request = useMemo<MetadataDesignRunRequest>(
    () => {
      const trimmedTableNameHint = tableNameHint.trim();
      return {
        dbProfileId: DEFAULT_METADATA_PROFILE,
        message,
        conversationId,
        designInputs: {
          ...(trimmedTableNameHint ? { tableNameHint: trimmedTableNameHint } : {}),
        },
        options: {
          useLlmAnalysis: true,
          useAiToolOrchestration: true,
          llmProfileId: "openai_sp_semantic_analysis",
          maxCandidates: 5,
          generateDtoDraft: true,
          conversationMode,
        },
      };
    },
    [conversationId, conversationMode, message, tableNameHint],
  );

  useEffect(() => {
    setDbProfileId(DEFAULT_METADATA_PROFILE);
  }, [defaultDbProfileId]);

  useEffect(() => {
    if (!isLoading || startedAt === null) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading, startedAt]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return;
    }
    transcript.scrollTop = transcript.scrollHeight;
  }, [isLoading, runs.length]);

  async function submitDesign() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), DESIGN_TIMEOUT_MS);
    setError(null);
    setElapsedSeconds(0);
    setStartedAt(Date.now());
    setIsLoading(true);
    try {
      const response = await fetch("/api/metadata/design-runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw await readDesignError(response);
      }
      let nextRun = (await response.json()) as MetadataDesignRunStatus;
      setConversationId(nextRun.conversationId);
      while (nextRun.status === "QUEUED" || nextRun.status === "RUNNING") {
        await sleep(DESIGN_POLL_INTERVAL_MS, controller.signal);
        const pollResponse = await fetch(
          `/api/metadata/design-runs/${encodeURIComponent(nextRun.runId)}`,
          { signal: controller.signal },
        );
        if (!pollResponse.ok) {
          throw await readDesignError(pollResponse);
        }
        nextRun = (await pollResponse.json()) as MetadataDesignRunStatus;
      }
      if (nextRun.status === "SUCCEEDED" && nextRun.result) {
        setRun(nextRun);
        setRuns((current) => [...current, nextRun]);
        setConversationMode("REFINE_CURRENT");
        setMessage("");
      } else {
        throw {
          code: nextRun.error?.code ?? "METADATA_DESIGN_RUN_FAILED",
          message: nextRun.error?.message ?? "Metadata design run failed.",
        } satisfies DesignError;
      }
    } catch (caught) {
      setError(normalizeError(caught));
    } finally {
      window.clearTimeout(timeout);
      setIsLoading(false);
    }
  }

  function resetDesign() {
    setDbProfileId(DEFAULT_METADATA_PROFILE);
    setMessage("");
    setTableNameHint("");
    setConversationMode("NEW_DESIGN");
    setConversationId(null);
    setRuns([]);
    setRun(null);
    setError(null);
    setElapsedSeconds(0);
    setStartedAt(null);
  }

  return (
    <div className="stack">
      <section className="panel metadata-chat-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Metadata design chat</p>
            <h1>Table script and DTO preview</h1>
          </div>
          <span className="quiet-label">durable run</span>
        </div>

        <div className="metadata-chat-shell">
          <div
            ref={transcriptRef}
            className="metadata-chat-transcript"
            aria-label="Metadata design conversation"
          >
            {runs.length === 0 ? (
              <div className="chat-message chat-message--assistant">
                <strong>Assistant</strong>
                <p>Ready for a metadata-backed design preview.</p>
              </div>
            ) : null}
            {runs.map((item) => (
              <div className="chat-turn" key={item.runId}>
                <div className="chat-message chat-message--user">
                  <strong>User</strong>
                  <p>{item.request.message}</p>
                </div>
                {item.result ? (
                  <div className="chat-message chat-message--assistant">
                    <strong>Assistant</strong>
                    <p>{item.result.assistantMessage}</p>
                    <small>{item.result.tableProposal.tableName}</small>
                  </div>
                ) : null}
              </div>
            ))}
            {isLoading ? (
              <div className="chat-message chat-message--assistant" aria-live="polite">
                <strong>Assistant</strong>
                <p>{`Designing ${elapsedSeconds}s`}</p>
              </div>
            ) : null}
          </div>

          <div className="metadata-chat-composer" aria-label="Metadata design composer">
            <div className="metadata-chat-controls">
              <label>
                <span>Metadata profile</span>
                <select
                  value={dbProfileId}
                  disabled
                  aria-readonly="true"
                  onChange={() => setDbProfileId(DEFAULT_METADATA_PROFILE)}
                >
                  <option value={DEFAULT_METADATA_PROFILE}>
                    {fixedProfile.id} - {fixedProfile.database}
                  </option>
                </select>
              </label>
              <label>
                <span>Conversation mode</span>
                <select
                  value={conversationMode}
                  onChange={(event) =>
                    setConversationMode(event.target.value as MetadataDesignConversationMode)
                  }
                >
                  <option value="NEW_DESIGN">New design</option>
                  <option value="REFINE_CURRENT">Refine current</option>
                </select>
              </label>
              <label>
                <span>Table name hint</span>
                <input
                  value={tableNameHint}
                  placeholder={TABLE_NAME_HINT_PLACEHOLDER}
                  onChange={(event) => setTableNameHint(event.target.value)}
                />
              </label>
            </div>
            <label className="metadata-chat-message-field">
              <span>Message</span>
              <textarea
                className="metadata-chat-input"
                value={message}
                placeholder={messagePlaceholder}
                onChange={(event) => setMessage(event.target.value)}
              />
            </label>
            <div className="form-actions">
              <button
                type="button"
                className="secondary-action"
                onClick={resetDesign}
                disabled={isLoading}
              >
                Reset
              </button>
              <button type="button" onClick={submitDesign} disabled={!canSubmit}>
                {isLoading ? `Designing ${elapsedSeconds}s` : "Send message"}
              </button>
            </div>
            {conversationId ? <p className="quiet-label">Conversation {conversationId}</p> : null}
            {error ? (
              <div className="blocker-list" aria-live="polite">
                <article className="blocker-row">
                  <strong>{error.code}</strong>
                  <span>{error.message}</span>
                </article>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {run?.result ? (
        <div className="metadata-design-output-stack">
          <MetadataDesignResultView run={run} />
        </div>
      ) : null}
    </div>
  );
}

function MetadataDesignResultView({ run }: Readonly<{ run: MetadataDesignRunStatus }>) {
  const result = run.result;
  const [originalMappings, setOriginalMappings] = useState<EditableMappingRow[]>([]);
  const [editableMappings, setEditableMappings] = useState<EditableMappingRow[]>([]);
  const [mappingValidationTouched, setMappingValidationTouched] = useState(false);
  const [generatedPreview, setGeneratedPreview] = useState<RegeneratedPreview | null>(null);
  const rowsSignature = useMemo(
    () => mappingRowsSignature(editableMappings),
    [editableMappings],
  );
  const originalRowsSignature = useMemo(
    () => mappingRowsSignature(originalMappings),
    [originalMappings],
  );
  const validationErrors = useMemo(
    () => validateEditableMappings(editableMappings),
    [editableMappings],
  );
  const currentGeneratedPreview =
    generatedPreview?.rowsSignature === rowsSignature ? generatedPreview : null;
  const mappingHasChanges =
    Boolean(editableMappings.length) && rowsSignature !== originalRowsSignature;

  useEffect(() => {
    if (!result) {
      return;
    }
    const rows = buildEditableMappingRows(result);
    setOriginalMappings(rows);
    setEditableMappings(rows);
    setGeneratedPreview(null);
    setMappingValidationTouched(false);
  }, [result, run.runId]);

  if (!result) {
    return null;
  }
  const activeResult = result;
  const tableProposal = activeResult.tableProposal;
  const dtoDraft = currentGeneratedPreview?.dtoDraft ?? activeResult.dtoDraft;
  const tableScriptPreview =
    currentGeneratedPreview?.createTableScriptPreview ??
    tableProposal.createTableScriptPreview;

  function updateEditableMapping(
    rowId: string,
    field: EditableMappingField,
    value: string,
  ) {
    setEditableMappings((current) =>
      current.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)),
    );
  }

  function updateEditableNullability(rowId: string, nullable: boolean) {
    setEditableMappings((current) =>
      current.map((row) => (row.id === rowId ? { ...row, nullable } : row)),
    );
  }

  function regeneratePreviews() {
    setMappingValidationTouched(true);
    if (validationErrors.length > 0) {
      return;
    }
    setGeneratedPreview(buildRegeneratedPreview(activeResult, editableMappings, rowsSignature));
  }

  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Design result</p>
            <h2>{tableProposal.tableName}</h2>
          </div>
          <StatusPill
            value={activeResult.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
            label={activeResult.reviewRequired ? "REVIEW_REQUIRED" : "Evidence bound"}
          />
        </div>
        <p className="lede">{activeResult.assistantMessage}</p>
        <dl className="metric-grid">
          <div>
            <dt>Run</dt>
            <dd>{run.runId}</dd>
          </div>
          <div>
            <dt>Intent</dt>
            <dd>{activeResult.interpretedIntent.intent}</dd>
          </div>
          <div>
            <dt>Columns</dt>
            <dd>{tableProposal.columns.length}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Interpreted intent</p>
            <h2>{activeResult.interpretedIntent.tableNameCandidate ?? tableProposal.tableName}</h2>
          </div>
          <StatusPill
            value={String(Math.round(activeResult.interpretedIntent.confidence * 100))}
            label="confidence"
          />
        </div>
        <div className="metadata-result-list">
          {activeResult.appliedChanges.map((change, index) => (
            <article
              className="metadata-result-row"
              key={`${change.action}-${change.target ?? index}`}
            >
              <div>
                <p className="eyebrow">{change.action}</p>
                <h3>{change.target ?? "review target"}</h3>
                <p>{change.summary}</p>
              </div>
              <div className="metadata-result-detail">
                <StatusPill
                  value={change.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
                  label={change.reviewRequired ? "review" : "changed"}
                />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Standardization</p>
            <h2>Field mappings</h2>
          </div>
          <button type="button" className="secondary-action" onClick={regeneratePreviews}>
            Regenerate previews
          </button>
        </div>
        {mappingHasChanges ? (
          <p className="quiet-label">Regenerate previews to use edited mappings.</p>
        ) : null}
        {validationErrors.length > 0 && mappingValidationTouched ? (
          <div className="blocker-list" aria-live="polite">
            {validationErrors.map((error) => (
              <article
                className="blocker-row"
                key={`${error.rowId}-${error.field}-${error.message}`}
              >
                <strong>{mappingRowLabel(editableMappings, error.rowId)}</strong>
                <span>{error.message}</span>
              </article>
            ))}
          </div>
        ) : null}
        <div className="data-table-wrap">
          <table className="data-table metadata-mapping-table">
            <thead>
              <tr>
                <th>Input</th>
                <th>Field name</th>
                <th>DB type</th>
                <th>Nullable</th>
                <th>Description</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {editableMappings.map((mapping) => (
                <tr key={mapping.id}>
                  <td>
                    <strong>{mapping.inputName || "-"}</strong>
                    {mapping.inputDescription ? <small>{mapping.inputDescription}</small> : null}
                  </td>
                  <td>
                    <input
                      value={mapping.proposedName}
                      aria-label={`Field name for ${mapping.inputName || mapping.proposedName}`}
                      onChange={(event) =>
                        updateEditableMapping(
                          mapping.id,
                          "proposedName",
                          event.target.value,
                        )
                      }
                    />
                    <MappingFieldError
                      errors={validationErrors}
                      rowId={mapping.id}
                      field="proposedName"
                    />
                  </td>
                  <td>
                    <input
                      value={mapping.proposedType}
                      aria-label={`DB type for ${mapping.proposedName}`}
                      onChange={(event) =>
                        updateEditableMapping(
                          mapping.id,
                          "proposedType",
                          event.target.value,
                        )
                      }
                    />
                    <MappingFieldError
                      errors={validationErrors}
                      rowId={mapping.id}
                      field="proposedType"
                    />
                  </td>
                  <td>
                    <label className="mapping-checkbox">
                      <input
                        type="checkbox"
                        checked={mapping.nullable}
                        onChange={(event) =>
                          updateEditableNullability(mapping.id, event.target.checked)
                        }
                      />
                      <span>{mapping.nullable ? "NULL" : "NOT NULL"}</span>
                    </label>
                  </td>
                  <td>
                    <textarea
                      className="mapping-description-input"
                      value={mapping.description}
                      aria-label={`Description for ${mapping.proposedName}`}
                      onChange={(event) =>
                        updateEditableMapping(
                          mapping.id,
                          "description",
                          event.target.value,
                        )
                      }
                    />
                  </td>
                  <td>
                    <StatusPill
                      value={mapping.reviewRequired ? "REVIEW_REQUIRED" : mapping.source}
                      label={mapping.source}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Table script preview</p>
            <h2>{`${tableProposal.schema}.${tableProposal.tableName}`}</h2>
          </div>
          <button
            type="button"
            className="secondary-action"
            onClick={() =>
              downloadText(
                `${tableProposal.tableName}.sql`,
                tableScriptPreview,
                "text/plain;charset=utf-8",
              )
            }
          >
            Download SQL preview
          </button>
        </div>
        <div className="content-preview">
          <pre>{tableScriptPreview}</pre>
        </div>
      </section>

      {dtoDraft ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">DTO draft</p>
              <h2>{dtoDraft.fileName}</h2>
            </div>
            <button
              type="button"
              className="secondary-action"
              onClick={() =>
                downloadText(dtoDraft.fileName, dtoDraft.content, "text/x-java-source")
              }
            >
              Download DTO draft
            </button>
          </div>
          <div className="content-preview metadata-draft-preview">
            <pre>{dtoDraft.content}</pre>
          </div>
        </section>
      ) : null}

      <MetadataEvidenceCandidates result={activeResult} />
    </>
  );
}

function MetadataEvidenceCandidates({
  result,
}: Readonly<{ result: NonNullable<MetadataDesignRunStatus["result"]> }>) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Metadata evidence</p>
          <h2>Related candidates</h2>
        </div>
      </div>
      <div className="metadata-result-list">
        {result.relatedMetadata.map((item) => (
          <article className="metadata-result-row" key={`${item.kind}-${item.objectRef}`}>
            <div>
              <p className="eyebrow">{item.kind}</p>
              <h3>{item.objectRef}</h3>
              <p>{item.summary}</p>
            </div>
            <div className="metadata-result-detail">
              <StatusPill value={String(item.score)} label={`score ${item.score}`} />
              {item.evidenceRefs.slice(0, 4).map((ref) => (
                <code key={`${item.objectRef}-${ref}`}>{ref}</code>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function MappingFieldError({
  errors,
  rowId,
  field,
}: Readonly<{
  errors: MappingValidationError[];
  rowId: string;
  field: EditableMappingField;
}>) {
  const error = errors.find((item) => item.rowId === rowId && item.field === field);
  return error ? <small className="mapping-field-error">{error.message}</small> : null;
}

function buildEditableMappingRows(result: MetadataDesignResult): EditableMappingRow[] {
  const usedColumnIndexes = new Set<number>();
  return result.standardizationMappings.map((mapping, index) => {
    const proposalColumn = findProposalColumnForMapping(
      result.tableProposal.columns,
      mapping,
      index,
      usedColumnIndexes,
    );
    return {
      id: `mapping-${index}-${safePreviewText(mapping.proposedName)}`,
      inputName: safePreviewText(mapping.inputName),
      inputDescription: safePreviewText(mapping.inputDescription),
      proposedName: safePreviewText(mapping.proposedName),
      proposedType: safePreviewText(mapping.proposedType),
      nullable: proposalColumn?.nullable ?? true,
      description: safePreviewText(proposalColumn?.description ?? mapping.inputDescription),
      source: mapping.source,
      evidenceRefs: mapping.evidenceRefs,
      reviewRequired: mapping.reviewRequired,
      reviewReasons: mapping.reviewReasons,
    };
  });
}

function findProposalColumnForMapping(
  columns: MetadataTableProposalColumn[],
  mapping: MetadataStandardizationMapping,
  index: number,
  usedColumnIndexes: Set<number>,
): MetadataTableProposalColumn | undefined {
  const proposedName = standardIdentifier(mapping.proposedName);
  const matchingIndex = columns.findIndex(
    (column, columnIndex) =>
      !usedColumnIndexes.has(columnIndex) && standardIdentifier(column.name) === proposedName,
  );
  if (matchingIndex >= 0) {
    usedColumnIndexes.add(matchingIndex);
    return columns[matchingIndex];
  }
  if (index < columns.length && !usedColumnIndexes.has(index)) {
    usedColumnIndexes.add(index);
    return columns[index];
  }
  return undefined;
}

function validateEditableMappings(rows: EditableMappingRow[]): MappingValidationError[] {
  const errors: MappingValidationError[] = [];
  const seenNames = new Map<string, string>();
  for (const row of rows) {
    const fieldName = row.proposedName.trim();
    if (!fieldName) {
      errors.push({
        rowId: row.id,
        field: "proposedName",
        message: "Field name is required.",
      });
    } else if (!MSSQL_IDENTIFIER_RE.test(fieldName)) {
      errors.push({
        rowId: row.id,
        field: "proposedName",
        message: "Field name must start with a letter or underscore and use only letters, numbers, and underscores.",
      });
    } else {
      const duplicateKey = fieldName.toUpperCase();
      const firstRowId = seenNames.get(duplicateKey);
      if (firstRowId) {
        errors.push({
          rowId: row.id,
          field: "proposedName",
          message: `Field name duplicates ${mappingRowLabel(rows, firstRowId)}.`,
        });
      } else {
        seenNames.set(duplicateKey, row.id);
      }
    }

    const typeCheck = parseSupportedDbType(row.proposedType);
    if (!typeCheck.ok) {
      errors.push({
        rowId: row.id,
        field: "proposedType",
        message: typeCheck.message,
      });
    }
  }
  return errors;
}

function parseSupportedDbType(
  value: string,
): { ok: true; normalized: string } | { ok: false; message: string } {
  const normalized = value.trim().replace(/\s+/g, "").toUpperCase();
  if (!normalized) {
    return { ok: false, message: "DB type is required." };
  }
  const match = /^([A-Z0-9]+)(?:\(([^)]*)\))?$/.exec(normalized);
  if (!match) {
    return { ok: false, message: "DB type format is not supported." };
  }
  const base = match[1];
  const params = match[2];
  const lengthTypes = new Set(["CHAR", "VARCHAR", "NCHAR", "NVARCHAR", "BINARY", "VARBINARY"]);
  const noParamTypes = new Set([
    "TEXT",
    "NTEXT",
    "IMAGE",
    "TINYINT",
    "SMALLINT",
    "INT",
    "BIGINT",
    "MONEY",
    "SMALLMONEY",
    "BIT",
    "DATE",
    "DATETIME",
    "SMALLDATETIME",
    "UNIQUEIDENTIFIER",
  ]);
  if (lengthTypes.has(base)) {
    if (!params) {
      return { ok: false, message: `${base} requires a length or MAX.` };
    }
    if (params === "MAX") {
      return { ok: true, normalized: `${base}(MAX)` };
    }
    const length = parseInteger(params);
    const maxLength = base.startsWith("N") ? 4000 : 8000;
    if (length < 1 || length > maxLength) {
      return {
        ok: false,
        message: `${base} length must be between 1 and ${maxLength}, or MAX.`,
      };
    }
    return { ok: true, normalized: `${base}(${length})` };
  }
  if (base === "DECIMAL" || base === "NUMERIC") {
    const parts = params?.split(",").map((part) => parseInteger(part)) ?? [];
    if (parts.length !== 2) {
      return { ok: false, message: `${base} requires precision and scale.` };
    }
    const [precision, scale] = parts;
    if (precision < 1 || precision > 38 || scale < 0 || scale > precision) {
      return {
        ok: false,
        message: `${base} precision must be 1-38 and scale must be 0-precision.`,
      };
    }
    return { ok: true, normalized: `${base}(${precision},${scale})` };
  }
  if (base === "DATETIME2" || base === "TIME") {
    if (!params) {
      return { ok: true, normalized: base };
    }
    const scale = parseInteger(params);
    if (scale < 0 || scale > 7) {
      return { ok: false, message: `${base} scale must be between 0 and 7.` };
    }
    return { ok: true, normalized: `${base}(${scale})` };
  }
  if (noParamTypes.has(base)) {
    if (params) {
      return { ok: false, message: `${base} does not accept length or scale here.` };
    }
    return { ok: true, normalized: base };
  }
  return { ok: false, message: `${base} is not supported by the preview generator.` };
}

function buildRegeneratedPreview(
  result: MetadataDesignResult,
  rows: EditableMappingRow[],
  rowsSignature: string,
): RegeneratedPreview {
  const columns = buildPreviewColumns(result, rows);
  const createTableScriptPreview = renderCreateTablePreview({
    schemaName: result.tableProposal.schema,
    tableName: result.tableProposal.tableName,
    tableDescription: safePreviewText(result.tableProposal.tableDescription),
    columns,
    reviewReasons: result.tableProposal.reviewReasons,
  });
  return {
    rowsSignature,
    createTableScriptPreview,
    dtoDraft: buildRegeneratedDtoDraft(result, columns),
  };
}

function buildPreviewColumns(
  result: MetadataDesignResult,
  rows: EditableMappingRow[],
): PreviewColumn[] {
  const originalMappingNames = new Set(
    result.standardizationMappings.map((mapping) => standardIdentifier(mapping.proposedName)),
  );
  const columns: PreviewColumn[] = rows.map((row) => {
    const normalizedType = parseSupportedDbType(row.proposedType);
    return {
      name: row.proposedName.trim(),
      dataType: normalizedType.ok ? normalizedType.normalized : row.proposedType.trim(),
      nullable: row.nullable,
      description: safePreviewText(row.description),
      source:
        row.source === "METADATA"
          ? "METADATA"
          : row.source === "STANDARD_POLICY"
            ? "STANDARD_POLICY"
            : "REVIEW_REQUIRED",
      evidenceRefs: row.evidenceRefs,
      reviewRequired: row.reviewRequired,
      reviewReasons: row.reviewReasons,
    };
  });
  const existingNames = new Set(columns.map((column) => standardIdentifier(column.name)));
  for (const column of result.tableProposal.columns) {
    const columnName = standardIdentifier(column.name);
    if (originalMappingNames.has(columnName) || existingNames.has(columnName)) {
      continue;
    }
    columns.push({
      name: column.name,
      dataType: column.dataType,
      nullable: column.nullable,
      description: safePreviewText(column.description),
      source: column.source,
      evidenceRefs: column.evidenceRefs,
      reviewRequired: column.reviewRequired,
      reviewReasons: column.reviewReasons,
    });
    existingNames.add(columnName);
  }
  return columns;
}

function renderCreateTablePreview({
  schemaName,
  tableName,
  tableDescription,
  columns,
  reviewReasons,
}: Readonly<{
  schemaName: string;
  tableName: string;
  tableDescription: string;
  columns: PreviewColumn[];
  reviewReasons: string[];
}>) {
  const lines = [
    "-- REVIEW_REQUIRED: metadata design preview only; manual schema check required.",
    "-- This script is not executed by the platform.",
    ...reviewReasons.map((reason) => `-- ${reason}`),
    `CREATE TABLE [${schemaName}].[${tableName}] (`,
  ];
  lines.push(
    columns
      .map((column) => {
        const nullability = column.nullable ? "NULL" : "NOT NULL";
        const refs = column.evidenceRefs.length ? column.evidenceRefs.join(", ") : "client-edit";
        const status = column.reviewRequired ? "REVIEW_REQUIRED" : column.source;
        return `    [${column.name}] ${column.dataType} ${nullability} -- evidence: ${refs}; ${status}`;
      })
      .join(",\n"),
  );
  lines.push(");");
  lines.push(
    ...renderDescriptionPreview({
      schemaName,
      tableName,
      tableDescription,
      columns,
    }),
  );
  return ensureTrailingNewline(lines.join("\n"));
}

function renderDescriptionPreview({
  schemaName,
  tableName,
  tableDescription,
  columns,
}: Readonly<{
  schemaName: string;
  tableName: string;
  tableDescription: string;
  columns: PreviewColumn[];
}>) {
  const lines = [
    "",
    "-- REVIEW_REQUIRED: MS_Description preview only; manual schema check required.",
  ];
  if (tableDescription) {
    lines.push(
      "-- REVIEW_REQUIRED: table description must be confirmed during manual schema check.",
      extendedPropertySql({
        value: tableDescription,
        schemaName,
        tableName,
      }),
    );
  }
  for (const column of columns) {
    const description = safePreviewText(column.description);
    if (!description) {
      lines.push(`-- REVIEW_REQUIRED: [${column.name}] has no confirmed description.`);
      continue;
    }
    if (column.reviewRequired) {
      const reasons = column.reviewReasons.join("; ") || "column metadata requires review";
      lines.push(`-- REVIEW_REQUIRED: [${column.name}] ${reasons}`);
    }
    lines.push(
      extendedPropertySql({
        value: description,
        schemaName,
        tableName,
        columnName: column.name,
      }),
    );
  }
  return lines;
}

function extendedPropertySql({
  value,
  schemaName,
  tableName,
  columnName,
}: Readonly<{
  value: string;
  schemaName: string;
  tableName: string;
  columnName?: string;
}>) {
  const parts = [
    "EXEC sys.sp_addextendedproperty",
    "    @name = N'MS_Description',",
    `    @value = N'${escapeSqlUnicodeLiteral(value)}',`,
    "    @level0type = N'SCHEMA',",
    `    @level0name = N'${escapeSqlUnicodeLiteral(schemaName)}',`,
    "    @level1type = N'TABLE',",
    `    @level1name = N'${escapeSqlUnicodeLiteral(tableName)}'`,
  ];
  if (columnName) {
    parts[parts.length - 1] = `${parts[parts.length - 1]},`;
    parts.push(
      "    @level2type = N'COLUMN',",
      `    @level2name = N'${escapeSqlUnicodeLiteral(columnName)}'`,
    );
  }
  parts[parts.length - 1] = `${parts[parts.length - 1]};`;
  return parts.join("\n");
}

function buildRegeneratedDtoDraft(
  result: MetadataDesignResult,
  columns: PreviewColumn[],
): MetadataGeneratedDraft | null {
  const original = result.dtoDraft;
  if (!original) {
    return null;
  }
  const tableProposal = result.tableProposal;
  const className = dtoClassNameForTable(tableProposal.tableName);
  const fields = columns.map((column) => ({
    javaType: javaTypeForDbType(column.dataType),
    fieldName: snakeToLowerCamel(column.name.toLowerCase()),
    column,
  }));
  const imports = javaImportsForTypes(fields.map((field) => field.javaType));
  const packageName = packageNameFromJavaContent(original.content);
  const lines = [
    `package ${packageName};`,
    "",
    ...imports.map((name) => `import ${name};`),
    ...(imports.length ? [""] : []),
    "/**",
    " * REVIEW_REQUIRED: Generated from metadata design preview evidence.",
    ` * Source table proposal: ${tableProposal.schema}.${tableProposal.tableName}`,
    " */",
    `public class ${className} {`,
  ];
  for (const field of fields) {
    const description = javaCommentText(field.column.description || field.column.name);
    const refs = field.column.evidenceRefs.length
      ? field.column.evidenceRefs.join(", ")
      : "client-edit";
    lines.push(
      `    /** ${description}; evidence=${refs}; ${
        field.column.reviewRequired ? "REVIEW_REQUIRED" : field.column.source
      } */`,
      `    private ${field.javaType} ${field.fieldName};`,
      "",
    );
  }
  lines.push("}");
  return {
    ...original,
    objectRef: `${tableProposal.schema}.${tableProposal.tableName}`,
    fileName: `${className}.java`,
    content: ensureTrailingNewline(lines.join("\n")),
    evidenceRefs: Array.from(
      new Set(columns.flatMap((column) => column.evidenceRefs)),
    ),
  };
}

function parseInteger(value: string | undefined): number {
  if (!value || !/^\d+$/.test(value)) {
    return Number.NaN;
  }
  return Number(value);
}

function standardIdentifier(value: string | null | undefined): string {
  return safePreviewText(value).toUpperCase();
}

function mappingRowsSignature(rows: EditableMappingRow[]): string {
  return JSON.stringify(
    rows.map((row) => ({
      name: row.proposedName.trim(),
      type: row.proposedType.trim(),
      nullable: row.nullable,
      description: safePreviewText(row.description),
    })),
  );
}

function mappingRowLabel(rows: EditableMappingRow[], rowId: string): string {
  const row = rows.find((item) => item.id === rowId);
  return row?.proposedName || row?.inputName || rowId;
}

function safePreviewText(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const text = value.trim();
  const lowered = text.toLowerCase();
  if (!text || lowered === "undefined" || lowered === "null" || lowered === "[object object]") {
    return "";
  }
  return text;
}

function escapeSqlUnicodeLiteral(value: string): string {
  return safePreviewText(value).replace(/'/g, "''").replace(/\r\n?/g, "\n").replace(/\n/g, "\\n");
}

function dtoClassNameForTable(tableName: string): string {
  const baseName = upperFirst(snakeToLowerCamel(tableName.toLowerCase()));
  return baseName.endsWith("Dto") ? baseName : `${baseName}Dto`;
}

function packageNameFromJavaContent(content: string): string {
  return /^package\s+([A-Za-z0-9_.]+);/m.exec(content)?.[1] ?? "com.pec.metadata.design.dto";
}

function snakeToLowerCamel(value: string): string {
  const parts = value.split("_").filter(Boolean);
  if (!parts.length) {
    return "field";
  }
  const [first, ...rest] = parts.map((part) => part.toLowerCase());
  return first + rest.map((part) => upperFirst(part)).join("");
}

function upperFirst(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

function javaTypeForDbType(dbType: string): string {
  const baseType = dbType.trim().toLowerCase().split("(", 1)[0];
  const mapping: Record<string, string> = {
    char: "String",
    varchar: "String",
    nchar: "String",
    nvarchar: "String",
    text: "String",
    ntext: "String",
    tinyint: "Integer",
    smallint: "Integer",
    int: "Integer",
    bigint: "Long",
    decimal: "BigDecimal",
    numeric: "BigDecimal",
    money: "BigDecimal",
    smallmoney: "BigDecimal",
    bit: "Boolean",
    date: "LocalDate",
    datetime: "LocalDateTime",
    datetime2: "LocalDateTime",
    smalldatetime: "LocalDateTime",
    time: "LocalTime",
    uniqueidentifier: "String",
    binary: "byte[]",
    varbinary: "byte[]",
    image: "byte[]",
  };
  return mapping[baseType] ?? "String";
}

function javaImportsForTypes(javaTypes: string[]): string[] {
  const imports = new Set<string>();
  if (javaTypes.includes("BigDecimal")) {
    imports.add("java.math.BigDecimal");
  }
  if (javaTypes.includes("LocalDate")) {
    imports.add("java.time.LocalDate");
  }
  if (javaTypes.includes("LocalDateTime")) {
    imports.add("java.time.LocalDateTime");
  }
  if (javaTypes.includes("LocalTime")) {
    imports.add("java.time.LocalTime");
  }
  return Array.from(imports);
}

function javaCommentText(value: string): string {
  return safePreviewText(value).replace(/\*\//g, "* /").replace(/\r?\n/g, " ");
}

function ensureTrailingNewline(text: string): string {
  return text.endsWith("\n") ? text : `${text}\n`;
}

function downloadText(fileName: string, content: string, contentType: string) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function sleep(durationMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Metadata design was aborted.", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, durationMs);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Metadata design was aborted.", "AbortError"));
      },
      { once: true },
    );
  });
}

async function readDesignError(response: Response): Promise<DesignError> {
  try {
    const payload = (await response.json()) as Partial<DesignError> & { detail?: unknown };
    return {
      code: typeof payload.code === "string" ? payload.code : "METADATA_DESIGN_BLOCKED",
      message:
        typeof payload.message === "string"
          ? payload.message
          : typeof payload.detail === "string"
            ? payload.detail
            : `HTTP ${response.status} ${response.statusText}`,
    };
  } catch {
    return {
      code: "METADATA_DESIGN_BLOCKED",
      message: `HTTP ${response.status} ${response.statusText}`,
    };
  }
}

function normalizeError(error: unknown): DesignError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return {
      code: "METADATA_DESIGN_TIMEOUT",
      message: "Metadata design exceeded 120 seconds.",
    };
  }
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error
  ) {
    return error as DesignError;
  }
  if (error instanceof Error) {
    return { code: "METADATA_DESIGN_BLOCKED", message: error.message };
  }
  return { code: "METADATA_DESIGN_BLOCKED", message: "Metadata design could not run." };
}
