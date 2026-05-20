"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import type {
  MetadataDesignRunRequest,
  MetadataDesignRunStatus,
  MetadataProfile,
} from "@/lib/api/types";

const DESIGN_TIMEOUT_MS = 120_000;
const DESIGN_POLL_INTERVAL_MS = 1_500;
const NEW_DESIGN_MESSAGE_PLACEHOLDER =
  "고객명, 주소, 주문일이 있는 주문 요청 테이블을 만들어줘.";
const REFINE_CURRENT_MESSAGE_PLACEHOLDER =
  "배송메모를 추가하고, 주문일은 날짜 타입으로 바꿔줘.";

interface DesignError {
  code: string;
  message: string;
}

type MetadataDesignConversationMode = NonNullable<
  MetadataDesignRunRequest["options"]
>["conversationMode"];

export function MetadataDesignChat({
  defaultDbProfileId,
  profiles,
}: Readonly<{
  defaultDbProfileId: string;
  profiles: MetadataProfile[];
}>) {
  const [dbProfileId, setDbProfileId] = useState(defaultDbProfileId);
  const [message, setMessage] = useState("");
  const [tableNameHint, setTableNameHint] = useState("PPM_ORDER_REQ");
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
    () => ({
      dbProfileId,
      message,
      conversationId,
      designInputs: {
        tableNameHint: tableNameHint || undefined,
      },
      options: {
        useLlmAnalysis: true,
        useAiToolOrchestration: true,
        llmProfileId: "openai_sp_semantic_analysis",
        maxCandidates: 5,
        generateDtoDraft: true,
        conversationMode,
      },
    }),
    [conversationId, conversationMode, dbProfileId, message, tableNameHint],
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
                  onChange={(event) => setDbProfileId(event.target.value)}
                >
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.id} - {profile.database}
                    </option>
                  ))}
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
  if (!result) {
    return null;
  }
  const dtoDraft = result.dtoDraft;
  const tableProposal = result.tableProposal;
  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Design result</p>
            <h2>{tableProposal.tableName}</h2>
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
            <dt>Intent</dt>
            <dd>{result.interpretedIntent.intent}</dd>
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
            <h2>{result.interpretedIntent.tableNameCandidate ?? tableProposal.tableName}</h2>
          </div>
          <StatusPill
            value={String(Math.round(result.interpretedIntent.confidence * 100))}
            label="confidence"
          />
        </div>
        <div className="metadata-result-list">
          {result.appliedChanges.map((change, index) => (
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
            <h2>{`${tableProposal.schema}.${tableProposal.tableName}`}</h2>
          </div>
          <button
            type="button"
            className="secondary-action"
            onClick={() =>
              downloadText(
                `${tableProposal.tableName}.sql`,
                tableProposal.createTableScriptPreview,
                "text/plain;charset=utf-8",
              )
            }
          >
            Download SQL preview
          </button>
        </div>
        <div className="content-preview">
          <pre>{tableProposal.createTableScriptPreview}</pre>
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

      <MetadataEvidenceCandidates result={result} />
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
