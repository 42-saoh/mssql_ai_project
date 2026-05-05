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
  const [job, artifactResponse, registryResponse, metadataSearch] = await Promise.all([
    api.getJob("job_demo_review_pending"),
    api.listJobArtifacts("job_demo_review_pending"),
    api.listRegistryVersions(),
    api.searchMetadataObjects({
      dbProfileId: "ppm",
      query: "P",
      objectTypes: ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
      limit: 6,
    }),
  ]);

  return (
    <div className="stack">
      <section className="panel portal-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Central portal shell</p>
            <h1>Analyze, validate, review</h1>
          </div>
          <span className="quiet-label">Mock data boundary</span>
        </div>
        <p className="lede">
          Product-demo App Router shell for MSSQL stored procedure request intake, read-only
          metadata search, draft artifacts, validation evidence, blockers, and approval-gated
          review state.
        </p>
        <div className="form-actions">
          <Link className="primary-action" href="/requests/new">
            Create PPM sample request
          </Link>
          <Link className="secondary-action" href="/metadata/search">
            Search metadata
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

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Metadata search</p>
              <h2>PPM identities</h2>
            </div>
            <StatusPill
              value={metadataSearch.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
              label={metadataSearch.reviewRequired ? "Review required" : "Evidence only"}
            />
          </div>
          <dl className="metric-grid">
            <div>
              <dt>Profile</dt>
              <dd>{metadataSearch.sourceProfile}</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>{metadataSearch.sourceDatabase}</dd>
            </div>
            <div>
              <dt>Results</dt>
              <dd>{metadataSearch.results.length}</dd>
            </div>
          </dl>
          {metadataSearch.blockers.length > 0 ? (
            <div className="blocker-list">
              {metadataSearch.blockers.map((blocker) => (
                <article className="blocker-row" key={blocker.code}>
                  <strong>{blocker.code}</strong>
                  <span>{blocker.message}</span>
                </article>
              ))}
            </div>
          ) : null}
          <Link href="/metadata/search">Open metadata search</Link>
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Review decision</p>
              <h2>Preview record</h2>
            </div>
            <span className="quiet-label">No publish</span>
          </div>
          <p className="lede">
            Reviewers can shape an approval decision payload while validation, audit, publish, and
            deployment boundaries stay explicit.
          </p>
          <div className="form-actions">
            <Link className="secondary-action" href="/review/decision">
              Preview decision
            </Link>
            <Link className="secondary-action" href="/jobs/job_demo_failed_blocker">
              View blocker job
            </Link>
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
