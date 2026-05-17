"use client";

import { useEffect, useMemo, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import type {
  MetadataDesignFieldInput,
  MetadataDesignRunRequest,
  MetadataDesignRunStatus,
  MetadataProfile,
} from "@/lib/api/types";

const DESIGN_TIMEOUT_MS = 120_000;
const DESIGN_POLL_INTERVAL_MS = 1_500;

interface DesignError {
  code: string;
  message: string;
}

export function MetadataDesignChat({
  defaultDbProfileId,
  profiles,
}: Readonly<{
  defaultDbProfileId: string;
  profiles: MetadataProfile[];
}>) {
  const [dbProfileId, setDbProfileId] = useState(defaultDbProfileId);
  const [message, setMessage] = useState(
    "Create an order request table with customer name, customer address, and order date.",
  );
  const [tableNameHint, setTableNameHint] = useState("PPM_ORDER_REQ");
  const [tableDescription, setTableDescription] = useState("Order request header");
  const [fields, setFields] = useState<MetadataDesignFieldInput[]>([
    { name: "CUSTOMER_NM", description: "Customer name" },
    { name: "CUSTOMER_ADDR", description: "Customer address" },
    { name: "ORDER_DT", description: "Order date" },
  ]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [run, setRun] = useState<MetadataDesignRunStatus | null>(null);
  const [error, setError] = useState<DesignError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const request = useMemo<MetadataDesignRunRequest>(
    () => ({
      dbProfileId,
      message,
      conversationId,
      designInputs: {
        tableNameHint,
        tableDescription,
        fields: fields.filter((field) => field.name || field.description || field.dbType),
      },
      options: {
        useLlmAnalysis: true,
        useAiToolOrchestration: true,
        llmProfileId: "openai_sp_semantic_analysis",
        maxCandidates: 5,
        generateDtoDraft: true,
      },
    }),
    [conversationId, dbProfileId, fields, message, tableDescription, tableNameHint],
  );

  useEffect(() => {
    if (!isLoading || startedAt === null) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading, startedAt]);

  async function submitDesign() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), DESIGN_TIMEOUT_MS);
    setRun(null);
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

  function addField() {
    setFields((current) => [...current, { name: "", description: "", dbType: "" }]);
  }

  function updateField(index: number, patch: MetadataDesignFieldInput) {
    setFields((current) =>
      current.map((field, fieldIndex) =>
        fieldIndex === index ? { ...field, ...patch } : field,
      ),
    );
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Metadata design chat</p>
            <h1>Table script and DTO preview</h1>
          </div>
          <span className="quiet-label">durable run</span>
        </div>
        <div className="form-grid">
          <label>
            <span>Metadata profile</span>
            <select value={dbProfileId} onChange={(event) => setDbProfileId(event.target.value)}>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.id} - {profile.database}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Table name hint</span>
            <input value={tableNameHint} onChange={(event) => setTableNameHint(event.target.value)} />
          </label>
          <label className="form-field--wide">
            <span>Message</span>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
          </label>
          <label className="form-field--wide">
            <span>Table description</span>
            <input
              value={tableDescription}
              onChange={(event) => setTableDescription(event.target.value)}
            />
          </label>
        </div>
        <fieldset className="metadata-design-fields">
          <legend>Fields</legend>
          <div className="metadata-design-field-grid">
            {fields.map((field, index) => (
              <div className="metadata-design-field-row" key={`field-${index}`}>
                <input
                  aria-label={`Field ${index + 1} name`}
                  value={field.name ?? ""}
                  onChange={(event) => updateField(index, { name: event.target.value })}
                  placeholder="FIELD_NM"
                />
                <input
                  aria-label={`Field ${index + 1} description`}
                  value={field.description ?? ""}
                  onChange={(event) => updateField(index, { description: event.target.value })}
                  placeholder="Field description"
                />
                <input
                  aria-label={`Field ${index + 1} type`}
                  value={field.dbType ?? ""}
                  onChange={(event) => updateField(index, { dbType: event.target.value })}
                  placeholder="VARCHAR(100)"
                />
              </div>
            ))}
          </div>
          <div className="form-actions">
            <button type="button" className="secondary-action" onClick={addField}>
              Add field
            </button>
            <button type="button" onClick={submitDesign} disabled={isLoading}>
              {isLoading ? `Designing ${elapsedSeconds}s` : "Generate preview"}
            </button>
          </div>
        </fieldset>
        {conversationId ? <p className="quiet-label">Conversation {conversationId}</p> : null}
        {error ? (
          <div className="blocker-list" aria-live="polite">
            <article className="blocker-row">
              <strong>{error.code}</strong>
              <span>{error.message}</span>
            </article>
          </div>
        ) : null}
      </section>

      {run?.result ? <MetadataDesignResultView run={run} /> : null}
    </div>
  );
}

function MetadataDesignResultView({ run }: Readonly<{ run: MetadataDesignRunStatus }>) {
  const result = run.result;
  if (!result) {
    return null;
  }
  const dtoDraft = result.dtoDraft;
  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Design result</p>
            <h2>{result.tableProposal.tableName}</h2>
          </div>
          <StatusPill
            value={result.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
            label={result.reviewRequired ? "REVIEW_REQUIRED" : "Evidence bound"}
          />
        </div>
        <p className="lede">{result.assistantMessage}</p>
        <dl className="metric-grid">
          <div>
            <dt>Run</dt>
            <dd>{run.runId}</dd>
          </div>
          <div>
            <dt>Metadata</dt>
            <dd>{result.relatedMetadata.length}</dd>
          </div>
          <div>
            <dt>Columns</dt>
            <dd>{result.tableProposal.columns.length}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Standardization</p>
            <h2>Field mappings</h2>
          </div>
        </div>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Input</th>
                <th>Proposed name</th>
                <th>Type</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {result.standardizationMappings.map((mapping) => (
                <tr key={`${mapping.proposedName}-${mapping.proposedType}`}>
                  <td>{mapping.inputName || mapping.inputDescription || "-"}</td>
                  <td>{mapping.proposedName}</td>
                  <td>{mapping.proposedType}</td>
                  <td>{mapping.source}</td>
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
            <h2>{`${result.tableProposal.schema}.${result.tableProposal.tableName}`}</h2>
          </div>
          <button
            type="button"
            className="secondary-action"
            onClick={() =>
              downloadText(
                `${result.tableProposal.tableName}.sql`,
                result.tableProposal.createTableScriptPreview,
                "text/plain;charset=utf-8",
              )
            }
          >
            Download SQL preview
          </button>
        </div>
        <div className="content-preview">
          <pre>{result.tableProposal.createTableScriptPreview}</pre>
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
    </>
  );
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
