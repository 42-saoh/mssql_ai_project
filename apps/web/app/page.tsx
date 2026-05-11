import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
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

export const dynamic = "force-dynamic";

function fulfilledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

function rejectedMessage(result: PromiseSettledResult<unknown>): string | null {
  return result.status === "rejected"
    ? formatPortalApiError(result.reason, "Portal API dependency is unavailable.")
    : null;
}

export default async function HomePage() {
  let api: PortalApi;
  try {
    api = getPortalApi();
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Portal API is not configured"
          message={formatPortalApiError(error, "PORTAL_API_BASE_URL is required.")}
        />
      </div>
    );
  }

  const [jobsResult, registryResult, metadataResult] = await Promise.allSettled([
    api.listJobs(5),
    api.listRegistryVersions(),
    api.searchMetadataObjects({
      dbProfileId: "ppm",
      query: "P",
      objectTypes: ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
      limit: 6,
    }),
  ]);
  const jobs = fulfilledValue<{ jobs: Job[] }>(jobsResult)?.jobs ?? [];
  const job = jobs[0] ?? null;
  const artifactResult = job ? await Promise.allSettled([api.listJobArtifacts(job.jobId)]) : null;
  const artifacts =
    artifactResult && artifactResult[0].status === "fulfilled"
      ? artifactResult[0].value.artifacts
      : [];
  const registryVersions =
    fulfilledValue<{ versions: RegistryVersion[] }>(registryResult)?.versions ?? [];
  const metadataSearch = fulfilledValue<MetadataSearchResponse>(metadataResult);
  const apiWarnings = [
    rejectedMessage(jobsResult),
    rejectedMessage(registryResult),
    rejectedMessage(metadataResult),
    artifactResult ? rejectedMessage(artifactResult[0]) : null,
  ].filter((message): message is string => Boolean(message));

  return (
    <div className="stack">
      <section className="panel portal-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Controlled live portal</p>
            <h1>Analyze and validate</h1>
          </div>
          <span className="quiet-label">HTTP API boundary</span>
        </div>
        <p className="lede">
          Portal pages call the configured API/BFF for request intake, read-only metadata search,
          draft artifacts, validation evidence, and blockers.
        </p>
        <div className="form-actions">
          <Link className="primary-action" href="/requests/new">
            Create PPM request
          </Link>
          <Link className="secondary-action" href="/metadata/search">
            Search metadata
          </Link>
          {job ? (
            <Link className="secondary-action" href={`/jobs/${job.jobId}`}>
              Inspect latest job
            </Link>
          ) : null}
        </div>
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Recent job</p>
              <h2>{job?.jobId ?? "No jobs returned"}</h2>
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
                The API is reachable only when PLF workflow prerequisites are configured.
              </p>
              <Link href="/requests/new">Create request</Link>
            </>
          )}
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Registry bindings</p>
              <h2>Active versions</h2>
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
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Artifact previews</p>
            <h2>Draft outputs</h2>
          </div>
        </div>
        <div className="artifact-list">
          {artifacts.map((artifact: ArtifactSummary) => (
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
