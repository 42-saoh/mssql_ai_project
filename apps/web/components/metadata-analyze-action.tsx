"use client";

import { useEffect, useMemo, useState } from "react";
import { MetadataAnalysisPanel } from "@/components/metadata-analysis-panel";
import type {
  MetadataAnalysisRequest,
  MetadataAnalysisResponse,
  MetadataAnalysisRunStatus,
  MetadataSearchObjectType,
} from "@/lib/api/types";

const ANALYSIS_TIMEOUT_MS = 120_000;
const ANALYSIS_POLL_INTERVAL_MS = 1_500;

interface AnalysisError {
  code: string;
  message: string;
}

export function MetadataAnalyzeAction({
  dbProfileId,
  query,
  objectTypes,
  defaultMaxTargets = 1,
}: Readonly<{
  dbProfileId: string;
  query: string;
  objectTypes: MetadataSearchObjectType[];
  defaultMaxTargets?: number;
}>) {
  const [analysis, setAnalysis] = useState<MetadataAnalysisResponse | null>(null);
  const [error, setError] = useState<AnalysisError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [maxTargets, setMaxTargets] = useState(String(clampMaxTargets(defaultMaxTargets)));
  const [generateDtoDrafts, setGenerateDtoDrafts] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);

  const request = useMemo<MetadataAnalysisRequest>(
    () => ({
      dbProfileId,
      query,
      objectTypes,
      options: {
        useLlmAnalysis: true,
        useAiToolOrchestration: true,
        llmProfileId: "openai_sp_semantic_analysis",
        maxTargets: clampMaxTargets(Number(maxTargets)),
        generateDtoDrafts,
      },
    }),
    [dbProfileId, generateDtoDrafts, maxTargets, objectTypes, query],
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

  async function runAnalysis() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);
    setAnalysis(null);
    setError(null);
    setElapsedSeconds(0);
    setRunId(null);
    setRunStatus(null);
    setStartedAt(Date.now());
    setIsLoading(true);
    try {
      const response = await fetch("/api/metadata/analysis-runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw await readAnalysisError(response);
      }
      let run = (await response.json()) as MetadataAnalysisRunStatus;
      setRunId(run.runId);
      setRunStatus(run.status);
      while (run.status === "QUEUED" || run.status === "RUNNING") {
        await sleep(ANALYSIS_POLL_INTERVAL_MS, controller.signal);
        const pollResponse = await fetch(
          `/api/metadata/analysis-runs/${encodeURIComponent(run.runId)}`,
          { signal: controller.signal },
        );
        if (!pollResponse.ok) {
          throw await readAnalysisError(pollResponse);
        }
        run = (await pollResponse.json()) as MetadataAnalysisRunStatus;
        setRunStatus(run.status);
      }
      if (run.status === "SUCCEEDED" && run.analysis) {
        setAnalysis(run.analysis);
      } else {
        const runError: AnalysisError = {
          code: run.error?.code ?? "AI_METADATA_ANALYSIS_RUN_FAILED",
          message: run.error?.message ?? "Metadata analysis run failed.",
        };
        throw runError;
      }
    } catch (caught) {
      setError(normalizeError(caught));
    } finally {
      window.clearTimeout(timeout);
      setIsLoading(false);
    }
  }

  return (
    <>
      <section className="panel metadata-analyze-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">AI-MCP metadata analysis</p>
            <h2>Evidence-bound draft insight</h2>
          </div>
          <span className="quiet-label">client async</span>
        </div>
        <p className="lede">
          Run metadata analysis without blocking the search page. Results stay evidence-bound and
          exclude row data, SQL definition text, execution, publish, deploy, or apply actions.
        </p>
        <div className="metadata-analyze-controls">
          <label>
            <span>Analysis target limit</span>
            <input
              min="1"
              max="5"
              type="number"
              value={maxTargets}
              onChange={(event) => setMaxTargets(event.target.value)}
              disabled={isLoading}
            />
          </label>
          <label className="inline-control">
            <input
              name="generateDtoDrafts"
              type="checkbox"
              checked={generateDtoDrafts}
              onChange={(event) => setGenerateDtoDrafts(event.target.checked)}
              disabled={isLoading}
            />
            <span>Generate DTO draft</span>
          </label>
          <div className="form-actions">
            <button type="button" onClick={runAnalysis} disabled={isLoading}>
              {isLoading ? "분석 중..." : "Analyze metadata"}
            </button>
            {isLoading ? (
              <span className="quiet-label" aria-live="polite">
                분석 중 {elapsedSeconds}s{runStatus ? ` - ${runStatus}` : ""}
              </span>
            ) : null}
          </div>
        </div>
        {runId ? <p className="quiet-label">Run {runId}</p> : null}
        {error ? (
          <div className="blocker-list" aria-live="polite">
            <article className="blocker-row">
              <strong>{error.code}</strong>
              <span>{error.message}</span>
            </article>
          </div>
        ) : null}
      </section>

      {analysis ? <MetadataAnalysisPanel analysis={analysis} /> : null}
    </>
  );
}

function clampMaxTargets(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(Math.max(Math.trunc(value), 1), 5);
}

function sleep(durationMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Metadata analysis was aborted.", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, durationMs);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Metadata analysis was aborted.", "AbortError"));
      },
      { once: true },
    );
  });
}

async function readAnalysisError(response: Response): Promise<AnalysisError> {
  try {
    const payload = (await response.json()) as Partial<AnalysisError> & {
      detail?: unknown;
    };
    return {
      code: typeof payload.code === "string" ? payload.code : "AI_METADATA_ANALYSIS_BLOCKED",
      message:
        typeof payload.message === "string"
          ? payload.message
          : typeof payload.detail === "string"
            ? payload.detail
            : `HTTP ${response.status} ${response.statusText}`,
    };
  } catch {
    return {
      code: "AI_METADATA_ANALYSIS_BLOCKED",
      message: `HTTP ${response.status} ${response.statusText}`,
    };
  }
}

function normalizeError(error: unknown): AnalysisError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return {
      code: "AI_METADATA_ANALYSIS_TIMEOUT",
      message: "Metadata analysis exceeded 120 seconds. Reduce the target limit and retry.",
    };
  }
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error
  ) {
    return error as AnalysisError;
  }
  if (error instanceof Error) {
    return { code: "AI_METADATA_ANALYSIS_BLOCKED", message: error.message };
  }
  return {
    code: "AI_METADATA_ANALYSIS_BLOCKED",
    message: "Metadata analysis could not run.",
  };
}
