import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { AgentRunSummary, Artifact, ValidationReport } from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  validationResultLabels,
  validationStatusLabels,
} from "@/lib/presentation";

const listItemKey = (scope: string, index: number) => `${scope}-${index}`;

function sameTargetHref(targetKey: string): string {
  return `/jobs?targetKey=${encodeURIComponent(targetKey)}`;
}

function displayRuleId(ruleId: string): string {
  return ruleId.replace(/review_required/gi, "evidence_caveat");
}

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
          {artifact.targetKey ? (
            <div>
              <dt>targetKey</dt>
              <dd>
                <code>{artifact.targetKey}</code>
              </dd>
            </div>
          ) : null}
        </dl>

        <div className="callout callout--warning">
          <strong>Draft-only boundary</strong>
          <p>
            This preview is draft-only. The default UI exposes no publish, deploy, SQL execution,
            DDL/DML apply, or source write action.
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
                  <h3>{displayRuleId(check.ruleId)}</h3>
                  <p>{check.message ?? "No message provided."}</p>
                </div>
                <div className="status-cluster">
                  <StatusPill value={check.severity} label={check.severity} />
                  <StatusPill value={check.result} label={validationResultLabels[check.result]} />
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
                    {run.status} - input {run.modelInvocation.inputHash} - tokens{" "}
                    {run.modelInvocation.tokenUsage?.totalTokens ?? 0} - latency{" "}
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
            {artifact.evidenceRefs.map((evidence, index) => (
              <article
                className="evidence-row"
                key={`${evidence.type}-${evidence.locator}-${index}`}
              >
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
              <p className="eyebrow">Validation caveats</p>
              <h2>Evidence notes</h2>
            </div>
          </div>

          {(validation?.qualityCaveats?.length ?? 0) > 0 ? (
            <div className="callout">
              <strong>Quality caveats</strong>
              <ul>
                {validation?.qualityCaveats?.map((item, index) => (
                  <li key={listItemKey("quality-caveat", index)}>{item}</li>
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
              <strong>근거 보강 필요</strong>
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
        {artifact.jobId ? <Link href={`/jobs/${artifact.jobId}`}>Back to job</Link> : null}
        {artifact.targetKey ? (
          <Link href={sameTargetHref(artifact.targetKey)}>Same target history</Link>
        ) : null}
      </div>
    </div>
  );
}
