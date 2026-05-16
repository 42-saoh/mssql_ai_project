import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { ArtifactSummary, Job, RequestedOutputType, TargetObject } from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  jobStatusLabels,
  outputLabels,
} from "@/lib/presentation";

export type JobArtifactLookup = Record<
  string,
  { artifacts: ArtifactSummary[]; error?: string }
>;

export function targetLabel(target?: TargetObject): string {
  if (!target) {
    return "Target unavailable";
  }
  return `${target.schema}.${target.name}`;
}

function formatDateTime(value?: string): string {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function outputSummary(outputs?: RequestedOutputType[]): string {
  if (!outputs?.length) {
    return "Outputs not recorded";
  }
  return outputs.map((output) => outputLabels[output] ?? output).join(", ");
}

export function AnalysisHistoryList({
  jobs,
  artifactsByJob,
  compact = false,
}: Readonly<{
  jobs: Job[];
  artifactsByJob: JobArtifactLookup;
  compact?: boolean;
}>) {
  if (jobs.length === 0) {
    return (
      <div className="callout">
        <strong>No analysis history</strong>
        <p>Submit a draft request to create the first workflow job.</p>
      </div>
    );
  }

  return (
    <div className={compact ? "history-list history-list--compact" : "history-list"}>
      {jobs.map((job) => {
        const artifactState = artifactsByJob[job.jobId] ?? { artifacts: [] };
        const artifacts = artifactState.artifacts;

        return (
          <article className="history-row" key={job.jobId}>
            <div className="history-main">
              <div className="history-title-row">
                <div>
                  <p className="eyebrow">{job.dbProfileId ?? "profile n/a"}</p>
                  <h3>{targetLabel(job.target)}</h3>
                </div>
                <StatusPill value={job.status} label={jobStatusLabels[job.status]} />
              </div>
              <dl className="history-meta">
                <div>
                  <dt>Job</dt>
                  <dd>{job.jobId}</dd>
                </div>
                <div>
                  <dt>Request</dt>
                  <dd>{job.requestId}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatDateTime(job.updatedAt ?? job.createdAt)}</dd>
                </div>
                <div>
                  <dt>Outputs</dt>
                  <dd>{outputSummary(job.outputs)}</dd>
                </div>
              </dl>
              {job.blockers?.length ? (
                <div className="history-caveats">
                  {job.blockers.map((blocker) => (
                    <span key={`${job.jobId}-${blocker.code}`}>
                      {blocker.code}: {blocker.message}
                    </span>
                  ))}
                </div>
              ) : null}
              {job.caveats?.length ? (
                <div className="history-caveats">
                  {job.caveats.map((caveat) => (
                    <span key={`${job.jobId}-${caveat}`}>{caveat}</span>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="history-actions">
              <Link href={`/jobs/${job.jobId}`}>Open job</Link>
              {artifactState.error ? (
                <span className="history-error">{artifactState.error}</span>
              ) : null}
              {artifacts.slice(0, compact ? 3 : 8).map((artifact) => (
                <Link href={`/artifacts/${artifact.artifactId}`} key={artifact.artifactId}>
                  {artifact.title ?? artifactTypeLabels[artifact.type]}{" "}
                  <span>
                    {artifactStatusLabels[artifact.status]} -{" "}
                    {formatCoverage(artifact.evidenceCoverage)}
                  </span>
                </Link>
              ))}
              {artifacts.length > (compact ? 3 : 8) ? (
                <small>{artifacts.length - (compact ? 3 : 8)} more artifacts in job detail</small>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
