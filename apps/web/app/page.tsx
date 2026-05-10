import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import type {
  ArtifactSummary,
  Job,
  MetadataSearchResponse,
  RegistryVersion,
} from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  jobStatusLabels,
} from "@/lib/presentation";

const demoJobId = "job_demo_review_pending";

function fulfilledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

function rejectedMessage(result: PromiseSettledResult<unknown>): string | null {
  return result.status === "rejected" && result.reason instanceof Error
    ? result.reason.message
    : null;
}

export default async function HomePage() {
  const api = getPortalApi();
  const [jobResult, artifactResult, registryResult, metadataResult] = await Promise.allSettled([
    api.getJob(demoJobId),
    api.listJobArtifacts(demoJobId),
    api.listRegistryVersions(),
    api.searchMetadataObjects({
      dbProfileId: "ppm",
      query: "P",
      objectTypes: ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
      limit: 6,
    }),
  ]);
  const job = fulfilledValue<Job>(jobResult);
  const artifacts = fulfilledValue<{ jobId: string; artifacts: ArtifactSummary[] }>(
    artifactResult,
  )?.artifacts ?? [];
  const registryVersions =
    fulfilledValue<{ versions: RegistryVersion[] }>(registryResult)?.versions ?? [];
  const metadataSearch = fulfilledValue<MetadataSearchResponse>(metadataResult);
  const apiWarnings = [
    rejectedMessage(jobResult),
    rejectedMessage(artifactResult),
    rejectedMessage(registryResult),
    rejectedMessage(metadataResult),
  ].filter((message): message is string => Boolean(message));

  return (
    <div className="stack">
      <section className="panel portal-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Central portal shell</p>
            <h1>Analyze, validate, review</h1>
          </div>
          <span className="quiet-label">{job ? "Mock data boundary" : "HTTP API boundary"}</span>
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
          {job ? (
            <Link className="secondary-action" href={`/jobs/${job.jobId}`}>
              Inspect review job
            </Link>
          ) : null}
        </div>
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Job status</p>
              <h2>{job?.jobId ?? "No demo job"}</h2>
            </div>
            {job ? <StatusPill value={job.status} label={jobStatusLabels[job.status]} /> : null}
          </div>
          {job ? (
            <>
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
            </>
          ) : (
            <>
              <p className="lede">
                The connected API is live, but it does not seed the mock demo job.
              </p>
              <Link href="/requests/new">Create request</Link>
            </>
          )}
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Registry bindings</p>
              <h2>Active mock versions</h2>
            </div>
          </div>
          <div className="registry-list">
            {registryVersions.map((version) => (
              <div key={`${version.registryType}-${version.version}`}>
                <strong>{version.registryType}</strong>
                <code>{version.version}</code>
              </div>
            ))}
          </div>
          {registryVersions.length === 0 ? (
            <p className="lede">Registry versions are unavailable from the connected API.</p>
          ) : null}
        </div>
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Metadata search</p>
              <h2>PPM identities</h2>
            </div>
            {metadataSearch ? (
              <StatusPill
                value={metadataSearch.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
                label={metadataSearch.reviewRequired ? "Review required" : "Evidence only"}
              />
            ) : null}
          </div>
          {metadataSearch ? (
            <>
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
            </>
          ) : (
            <p className="lede">Metadata search is unavailable from the connected API.</p>
          )}
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
          {artifacts.map((artifact) => (
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
        {artifacts.length === 0 ? (
          <p className="lede">Draft artifacts are unavailable until the connected API has a job.</p>
        ) : null}
      </section>

      {apiWarnings.length > 0 ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">HTTP adapter</p>
              <h2>Connected API notes</h2>
            </div>
          </div>
          <div className="blocker-list">
            {[...new Set(apiWarnings)].map((message) => (
              <article className="blocker-row" key={message}>
                <strong>HTTP_API_RESPONSE</strong>
                <span>{message}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
