import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { AgentRunSummary, Artifact, ValidationReport } from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  validationStatusLabels,
} from "@/lib/presentation";

const reviewChecklist = [
  "Evidence references point to metadata, static analysis, policy, or explicit user input.",
  "Assumptions marked REVIEW_REQUIRED are resolved by a human reviewer.",
  "Generated code or DDL remains draft-only until validation and approval are recorded.",
  "No screen in this shell executes SQL, publishes code, or mutates business data.",
];

const listItemKey = (scope: string, index: number) => `${scope}-${index}`;

export function ArtifactPreview({
  artifact,
  validation,
  agentRuns = [],
  validateAction,
}: Readonly<{
  artifact: Artifact;
  validation?: ValidationReport | null;
  agentRuns?: AgentRunSummary[];
  validateAction?: (formData: FormData) => Promise<void>;
}>) {
  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Artifact preview</p>
            <h1>{artifact.title ?? artifactTypeLabels[artifact.type]}</h1>
          </div>
          <StatusPill value={artifact.status} label={artifactStatusLabels[artifact.status]} />
        </div>

        <dl className="metric-grid">
          <div>
            <dt>Artifact id</dt>
            <dd>{artifact.artifactId}</dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>{artifactTypeLabels[artifact.type]}</dd>
          </div>
          <div>
            <dt>Evidence coverage</dt>
            <dd>{formatCoverage(artifact.evidenceCoverage)}</dd>
          </div>
          <div>
            <dt>Generator</dt>
            <dd>{artifact.generatorVersion}</dd>
          </div>
        </dl>

        <div className="callout callout--warning">
          <strong>Draft-only boundary</strong>
          <p>
            This preview is not published or deployed. Validation and reviewer decisions can be
            recorded later, but this UI exposes no SQL execution, DDL apply, source write, or
            publish action.
          </p>
        </div>

        {artifact.blockers?.length ? (
          <div className="blocker-list">
            {artifact.blockers.map((blocker) => (
              <article className="blocker-row" key={blocker.code}>
                <strong>{blocker.code}</strong>
                <span>{blocker.message}</span>
              </article>
            ))}
          </div>
        ) : null}

        {artifact.caveats?.length ? (
          <div className="callout">
            <strong>Caveats</strong>
            <ul>
              {artifact.caveats.map((caveat, index) => (
                <li key={listItemKey("artifact-caveat", index)}>{caveat}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="content-preview" aria-label="Draft artifact content">
          <pre>{artifact.content}</pre>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Validation</p>
            <h2>Evidence and policy checks</h2>
          </div>
          <StatusPill
            value={validation?.status ?? "REVIEW_REQUIRED"}
            label={validation ? validationStatusLabels[validation.status] : "Not recorded"}
          />
        </div>

        {validation ? (
          <div className="validation-list">
            {validation.checks.map((check) => (
              <article className="validation-row" key={check.ruleId}>
                <div>
                  <h3>{check.ruleId}</h3>
                  <p>{check.message ?? "No message provided."}</p>
                </div>
                <div className="status-cluster">
                  <StatusPill value={check.severity} label={check.severity} />
                  <StatusPill value={check.result} label={check.result.replace("_", " ")} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="callout callout--warning">
            <strong>No latest validation report</strong>
            <p>Run validation explicitly to create a PLF validation report for this artifact.</p>
          </div>
        )}

        {(validation?.missingEvidence?.length ?? 0) > 0 ? (
          <div className="callout callout--warning">
            <strong>Missing evidence</strong>
            <ul>
              {validation?.missingEvidence?.map((item, index) => (
                <li key={listItemKey("missing-evidence", index)}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {validateAction ? (
          <form action={validateAction} className="form-actions">
            <input name="artifactId" type="hidden" value={artifact.artifactId} />
            <button type="submit">Run validation</button>
          </form>
        ) : null}
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">LLM trace</p>
              <h2>Sanitized model run</h2>
            </div>
          </div>
          {agentRuns.length > 0 ? (
            <div className="evidence-list">
              {agentRuns.map((run) => (
                <article className="evidence-row" key={run.agentRunId}>
                  <strong>{run.modelInvocation.model}</strong>
                  <span>{run.modelInvocation.promptVersion}</span>
                  <code>{run.modelInvocation.outputHash}</code>
                  <small>
                    {run.status} · input {run.modelInvocation.inputHash} · tokens{" "}
                    {run.modelInvocation.tokenUsage?.totalTokens ?? 0} · latency{" "}
                    {run.modelInvocation.latencyMs ?? 0}ms
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <div className="callout">
              <strong>No LLM trace</strong>
              <p>This artifact was generated without a recorded LLM semantic analysis run.</p>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Evidence refs</p>
              <h2>Trace points</h2>
            </div>
          </div>
          <div className="evidence-list">
            {artifact.evidenceRefs.map((evidence) => (
              <article className="evidence-row" key={`${evidence.type}-${evidence.locator}`}>
                <strong>{evidence.type}</strong>
                <span>{evidence.objectRef}</span>
                <code>{evidence.locator}</code>
                {evidence.snapshotId ? <small>{evidence.snapshotId}</small> : null}
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Review</p>
              <h2>Checklist placeholder</h2>
            </div>
          </div>
          <ul className="checklist">
            {reviewChecklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          {(validation?.manualReviewPoints?.length ?? 0) > 0 ? (
            <div className="callout">
              <strong>Manual review points</strong>
              <ul>
                {validation?.manualReviewPoints?.map((item, index) => (
                  <li key={listItemKey("manual-review-point", index)}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {(artifact.assumptions?.length ?? 0) > 0 ? (
            <div className="callout">
              <strong>Assumptions</strong>
              <ul>
                {artifact.assumptions?.map((item, index) => (
                  <li key={listItemKey("artifact-assumption", index)}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {(artifact.todos?.length ?? 0) > 0 ? (
            <div className="callout callout--warning">
              <strong>TODO / REVIEW_REQUIRED</strong>
              <ul>
                {artifact.todos?.map((item, index) => (
                  <li key={listItemKey("artifact-todo", index)}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>

      <div className="page-actions">
        {artifact.jobId ? <Link href={`/jobs/${artifact.jobId}`}>Back to review job</Link> : null}
        <Link className="secondary-action" href={`/review/decision?artifactId=${artifact.artifactId}`}>
          Record review decision
        </Link>
      </div>
    </div>
  );
}
