import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  jobStatusLabels,
} from "@/lib/presentation";

export default async function HomePage() {
  const api = getPortalApi();
  const [job, artifactResponse, registryResponse] = await Promise.all([
    api.getJob("job_demo_review_pending"),
    api.listJobArtifacts("job_demo_review_pending"),
    api.listRegistryVersions(),
  ]);

  return (
    <div className="stack">
      <section className="panel portal-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Central portal shell</p>
            <h1>Request, validate, review</h1>
          </div>
          <span className="quiet-label">Mock data boundary</span>
        </div>
        <p className="lede">
          A minimal App Router shell for MSSQL stored procedure analysis requests, draft
          artifacts, evidence refs, and approval-gated review state.
        </p>
        <div className="form-actions">
          <Link className="primary-action" href="/requests/new">
            Create mock request
          </Link>
          <Link className="secondary-action" href="/jobs/job_demo_review_pending">
            Inspect review job
          </Link>
        </div>
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Job status</p>
              <h2>{job.jobId}</h2>
            </div>
            <StatusPill value={job.status} label={jobStatusLabels[job.status]} />
          </div>
          <dl className="metric-grid">
            <div>
              <dt>Request</dt>
              <dd>{job.requestId}</dd>
            </div>
            <div>
              <dt>Current gate</dt>
              <dd>{job.currentStep ?? "Draft intake"}</dd>
            </div>
          </dl>
          <Link href={`/jobs/${job.jobId}`}>Open job detail</Link>
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Registry bindings</p>
              <h2>Active mock versions</h2>
            </div>
          </div>
          <div className="registry-list">
            {registryResponse.versions.map((version) => (
              <div key={`${version.registryType}-${version.version}`}>
                <strong>{version.registryType}</strong>
                <code>{version.version}</code>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Artifact previews</p>
            <h2>Draft outputs</h2>
          </div>
        </div>
        <div className="artifact-list">
          {artifactResponse.artifacts.map((artifact) => (
            <article className="artifact-row" key={artifact.artifactId}>
              <div>
                <h3>{artifact.title ?? artifactTypeLabels[artifact.type]}</h3>
                <p>
                  {artifactTypeLabels[artifact.type]} · evidence coverage{" "}
                  {formatCoverage(artifact.evidenceCoverage)}
                </p>
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
