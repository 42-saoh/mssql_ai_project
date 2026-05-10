import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { AgentRunSummary, ArtifactSummary, Job } from "@/lib/api/types";
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
  "REVIEW",
] as const;

function stepState(job: Job, step: (typeof workflowSteps)[number]) {
  if (job.status === "APPROVED" || job.status === "REJECTED") {
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
}: Readonly<{
  job: Job;
  scenarioSummary: string;
  artifacts: ArtifactSummary[];
  agentRuns: AgentRunSummary[];
}>) {
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
        </dl>

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
            <p className="eyebrow">Approval-gated flow</p>
            <h2>Draft to review status</h2>
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
          <div className="validation-list">
            {agentRuns.map((run) => (
              <article className="validation-row" key={run.agentRunId}>
                <div>
                  <h3>{run.agentType}</h3>
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
                  {artifact.reviewRequired ? " · REVIEW_REQUIRED" : ""}
                </p>
                {artifact.caveats?.length ? <small>{artifact.caveats.join(", ")}</small> : null}
              </div>
              <div className="row-actions">
                <StatusPill
                  value={artifact.status}
                  label={artifactStatusLabels[artifact.status]}
                />
                <Link href={`/artifacts/${artifact.artifactId}`}>Preview</Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
