import Link from "next/link";
import { JobAutoRefresh } from "@/components/job-auto-refresh";
import { StatusPill } from "@/components/status-pill";
import type {
  AgentRunSummary,
  ArtifactSummary,
  Job,
  KnowledgeAssetSummary,
} from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  jobStatusLabels,
  workflowStepLabels,
} from "@/lib/presentation";

const workflowSteps = [
  "COLLECT_METADATA",
  "ANALYZE",
  "GENERATE",
  "VALIDATE",
] as const;

const dependencyAgentType = "LLM_SEMANTIC_ANALYST_DEPENDENCY";
const skippedDependencyDisplayLimit = 8;

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordsFrom(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function textValue(value: unknown, fallback = "n/a") {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return fallback;
}

function countValue(value: unknown) {
  return textValue(value, "0");
}

function dependencyAnalysisFromRun(run: AgentRunSummary): UnknownRecord | null {
  const sourceContextSummary = run.modelInvocation.sourceContextSummary;
  if (!isRecord(sourceContextSummary)) {
    return null;
  }
  const dependencyAnalysis = sourceContextSummary.dependencyAnalysis;
  return isRecord(dependencyAnalysis) ? dependencyAnalysis : null;
}

function rootDependencyAnalysis(agentRuns: AgentRunSummary[]): UnknownRecord | null {
  const rootRun = agentRuns.find(
    (run) => run.agentType !== dependencyAgentType && dependencyAnalysisFromRun(run),
  );
  return rootRun ? dependencyAnalysisFromRun(rootRun) : null;
}

function sourceContextDigest(value: unknown) {
  if (!isRecord(value)) {
    return "source context n/a";
  }
  return [
    `mode ${textValue(value.mode)}`,
    `budget ${textValue(value.budgetStatus)}`,
    `selected spans ${countValue(value.selectedSpanCount)}`,
    `skipped spans ${countValue(value.skippedSpanCount)}`,
  ].join(" - ");
}

function dependencyTargetKey(item: UnknownRecord, index: number) {
  return `${textValue(item.targetKey, textValue(item.targetRef, "dependency"))}-${textValue(
    item.agentRunId,
    String(index),
  )}`;
}

function sameTargetHref(targetKey: string): string {
  return `/jobs?targetKey=${encodeURIComponent(targetKey)}`;
}

function stepState(job: Job, step: (typeof workflowSteps)[number]) {
  if (job.status === "VALIDATION_COMPLETE") {
    return "done";
  }

  if (job.status === "FAILED" && job.currentStep === step) {
    return "failed";
  }

  if (job.currentStep === step) {
    return "current";
  }

  const currentIndex = job.currentStep
    ? workflowSteps.findIndex((workflowStep) => workflowStep === job.currentStep)
    : -1;
  const stepIndex = workflowSteps.indexOf(step);

  return currentIndex > stepIndex ? "done" : "pending";
}

export function JobStatusView({
  job,
  scenarioSummary,
  artifacts,
  agentRuns,
  knowledgeAssets,
}: Readonly<{
  job: Job;
  scenarioSummary: string;
  artifacts: ArtifactSummary[];
  agentRuns: AgentRunSummary[];
  knowledgeAssets: KnowledgeAssetSummary[];
}>) {
  const dependencyAnalysis = rootDependencyAnalysis(agentRuns);
  const analyzedTargets = recordsFrom(dependencyAnalysis?.analyzedTargets);
  const skippedTargets = recordsFrom(dependencyAnalysis?.skippedTargets);
  const visibleSkippedTargets = skippedTargets.slice(0, skippedDependencyDisplayLimit);
  const hiddenSkippedCount = Math.max(skippedTargets.length - visibleSkippedTargets.length, 0);
  const progressPercent = Math.round((job.progress ?? 0) * 100);

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Workflow job</p>
            <h1>{job.jobId}</h1>
          </div>
          <StatusPill value={job.status} label={jobStatusLabels[job.status]} />
        </div>

        <p className="lede">{scenarioSummary}</p>

        <dl className="metric-grid">
          <div>
            <dt>Request</dt>
            <dd>{job.requestId}</dd>
          </div>
          <div>
            <dt>Current step</dt>
            <dd>{job.currentStep ? workflowStepLabels[job.currentStep] : "Draft intake"}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{job.updatedAt ?? "Not available"}</dd>
          </div>
          <div>
            <dt>Progress</dt>
            <dd>{job.progress !== undefined ? `${Math.round(job.progress * 100)}%` : "Unknown"}</dd>
          </div>
          {job.targetKey ? (
            <div>
              <dt>targetKey</dt>
              <dd>
                <code>{job.targetKey}</code>
              </dd>
            </div>
          ) : null}
        </dl>

        <div className="progress-block">
          <div className="progress-label">
            <strong>Estimated progress</strong>
            <span>{progressPercent}%</span>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-label="Estimated progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent}
          >
            <span className="progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
          <p>Status-based estimate for visibility while the draft workflow runs.</p>
          <JobAutoRefresh status={job.status} />
        </div>

        {job.targetKey ? (
          <div className="form-actions">
            <Link className="secondary-action" href={sameTargetHref(job.targetKey)}>
              Same target history
            </Link>
          </div>
        ) : null}

        {job.failureReason ? (
          <div className="callout callout--warning">
            <strong>Failure reason</strong>
            <p>{job.failureReason}</p>
          </div>
        ) : null}

        {job.blockers?.length ? (
          <div className="blocker-list">
            {job.blockers.map((blocker) => (
              <article className="blocker-row" key={blocker.code}>
                <strong>{blocker.code}</strong>
                <span>{blocker.message}</span>
              </article>
            ))}
          </div>
        ) : null}

        {job.caveats?.length ? (
          <div className="callout">
            <strong>Caveats</strong>
            <ul>
              {job.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Validation flow</p>
            <h2>Draft to validation complete</h2>
          </div>
        </div>
        <ol className="timeline">
          {workflowSteps.map((step) => (
            <li className={`timeline-step timeline-step--${stepState(job, step)}`} key={step}>
              <span>{workflowStepLabels[step]}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Agent runtime</p>
            <h2>LLM trace summary</h2>
          </div>
          <span className="quiet-label">Sanitized</span>
        </div>

        {agentRuns.length > 0 ? (
          <>
            {dependencyAnalysis ? (
              <div className="dependency-summary">
                <dl className="metric-grid metric-grid--dense">
                  <div>
                    <dt>Mode</dt>
                    <dd>{textValue(dependencyAnalysis.mode)}</dd>
                  </div>
                  <div>
                    <dt>Requested depth</dt>
                    <dd>{countValue(dependencyAnalysis.requestedDepth)}</dd>
                  </div>
                  <div>
                    <dt>Selected</dt>
                    <dd>{countValue(dependencyAnalysis.selectedCount)}</dd>
                  </div>
                  <div>
                    <dt>Analyzed</dt>
                    <dd>{countValue(dependencyAnalysis.analyzedCount)}</dd>
                  </div>
                  <div>
                    <dt>Skipped</dt>
                    <dd>{countValue(dependencyAnalysis.skippedCount)}</dd>
                  </div>
                  <div>
                    <dt>Child runs</dt>
                    <dd>{countValue(dependencyAnalysis.childRunCount)}</dd>
                  </div>
                </dl>

                {analyzedTargets.length > 0 ? (
                  <div className="dependency-target-list">
                    {analyzedTargets.map((target, index) => (
                      <article
                        className="dependency-target-row"
                        key={dependencyTargetKey(target, index)}
                      >
                        <div>
                          <strong>{textValue(target.targetRef, "dependency target")}</strong>
                          <span>depth {textValue(target.depth)}</span>
                        </div>
                        <div className="dependency-target-meta">
                          <code>{textValue(target.agentRunId, "child run pending")}</code>
                          {target.targetKey ? <code>{textValue(target.targetKey)}</code> : null}
                          <span>{sourceContextDigest(target.sourceContextSummary)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : null}

                {skippedTargets.length > 0 ? (
                  <div className="callout callout--warning">
                    <strong>근거 보강 필요 dependencies</strong>
                    <p>
                      {countValue(dependencyAnalysis.skippedCount)} dependency targets need
                      stronger evidence. Showing {visibleSkippedTargets.length} of{" "}
                      {skippedTargets.length}
                      {hiddenSkippedCount > 0 ? `; ${hiddenSkippedCount} more are hidden.` : "."}
                    </p>
                    <ul>
                      {visibleSkippedTargets.map((target, index) => (
                        <li key={dependencyTargetKey(target, index)}>
                          {textValue(target.targetRef, "dependency target")} -{" "}
                          {textValue(target.reason, "근거 보강 필요")}
                          {target.targetKey ? ` - ${textValue(target.targetKey)}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="validation-list">
            {agentRuns.map((run) => (
              <article className="validation-row" key={run.agentRunId}>
                <div>
                  <div className="run-title-row">
                    <h3>{run.agentType}</h3>
                    <span className="quiet-label">
                      {run.agentType === dependencyAgentType ? "Dependency child" : "Root run"}
                    </span>
                  </div>
                  <small>
                    target {run.targetRef}
                    {run.targetKey ? ` - ${run.targetKey}` : ""}
                  </small>
                  <p>
                    {run.modelInvocation.model} · {run.modelInvocation.promptVersion} ·{" "}
                    {run.summary}
                  </p>
                  <small>
                    input {run.modelInvocation.inputHash} · output{" "}
                    {run.modelInvocation.outputHash} · tokens{" "}
                    {run.modelInvocation.tokenUsage?.totalTokens ?? 0} · latency{" "}
                    {run.modelInvocation.latencyMs ?? 0}ms
                  </small>
                </div>
                <div className="status-cluster">
                  <StatusPill value={run.status} label={run.status} />
                  <StatusPill
                    value={run.modelInvocation.reasoningEffort ?? "none"}
                    label={run.modelInvocation.reasoningEffort ?? "none"}
                  />
                </div>
              </article>
            ))}
            </div>
          </>
        ) : (
          <div className="callout">
            <strong>No LLM run recorded</strong>
            <p>Submit a request with LLM semantic analysis enabled to record a sanitized trace.</p>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Knowledge assets</p>
            <h2>Versioned fact graph</h2>
          </div>
          <span className="quiet-label">Sanitized</span>
        </div>

        {knowledgeAssets.length > 0 ? (
          <div className="artifact-list">
            {knowledgeAssets.map((asset) => (
              <article className="artifact-row" key={asset.assetId}>
                <div>
                  <h3>{asset.assetKind}</h3>
                  <p>
                    {asset.targetType} · {asset.targetSchema}.{asset.targetName} · v
                    {asset.currentVersionNo}
                  </p>
                  <small>content {asset.contentHash ?? "pending"}</small>
                  {asset.targetKey ? <small>targetKey {asset.targetKey}</small> : null}
                </div>
                <div className="row-actions">
                  <Link href={`/api/v1/knowledge/assets/${asset.assetId}`}>Open</Link>
                  {asset.targetKey ? (
                    <Link href={sameTargetHref(asset.targetKey)}>Same target history</Link>
                  ) : null}
                  {asset.currentVersionId ? (
                    <Link
                      href={`/api/v1/knowledge/assets/${asset.assetId}/versions/${asset.currentVersionId}/facts`}
                    >
                      Facts
                    </Link>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="callout">
            <strong>No knowledge asset recorded</strong>
            <p>Knowledge assetization may be disabled or awaiting the v5 schema.</p>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Draft artifacts</p>
            <h2>Preview outputs</h2>
          </div>
          <span className="quiet-label">HTTP API</span>
        </div>

        <div className="artifact-list">
          {artifacts.map((artifact) => (
            <article className="artifact-row" key={artifact.artifactId}>
              <div>
                <h3>{artifact.title ?? artifactTypeLabels[artifact.type]}</h3>
                <p>
                  {artifactTypeLabels[artifact.type]} · evidence coverage{" "}
                  {formatCoverage(artifact.evidenceCoverage)}
                  {artifact.reviewRequired ? " · 근거 보강 필요" : ""}
                </p>
                {artifact.caveats?.length ? <small>{artifact.caveats.join(", ")}</small> : null}
                {artifact.targetKey ? <small>targetKey {artifact.targetKey}</small> : null}
              </div>
              <div className="row-actions">
                <StatusPill
                  value={artifact.status}
                  label={artifactStatusLabels[artifact.status]}
                />
                {artifact.targetKey ? (
                  <Link href={sameTargetHref(artifact.targetKey)}>Same target history</Link>
                ) : null}
                <Link href={`/artifacts/${artifact.artifactId}`}>Preview</Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
