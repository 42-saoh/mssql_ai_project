import Link from "next/link";
import {
  AnalysisHistoryList,
  type JobArtifactLookup,
} from "@/components/analysis-history-list";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { Job, RegistryVersion } from "@/lib/api/types";

export const dynamic = "force-dynamic";

function fulfilledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

function rejectedMessage(result: PromiseSettledResult<unknown>): string | null {
  return result.status === "rejected"
    ? formatPortalApiError(result.reason, "Portal API dependency is unavailable.")
    : null;
}

async function artifactsForJobs(api: PortalApi, jobs: Job[]): Promise<JobArtifactLookup> {
  const results = await Promise.allSettled(
    jobs.map(async (job) => ({
      jobId: job.jobId,
      response: await api.listJobArtifacts(job.jobId),
    })),
  );
  return Object.fromEntries(
    results.map((result, index) => {
      const jobId = jobs[index].jobId;
      if (result.status === "fulfilled") {
        return [jobId, { artifacts: result.value.response.artifacts }];
      }
      return [
        jobId,
        {
          artifacts: [],
          error: formatPortalApiError(result.reason, "Artifacts unavailable."),
        },
      ];
    }),
  ) as JobArtifactLookup;
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

  const [jobsResult, registryResult] = await Promise.allSettled([
    api.listJobs(5),
    api.listRegistryVersions(),
  ]);
  const jobs = fulfilledValue<{ jobs: Job[] }>(jobsResult)?.jobs ?? [];
  const artifactsByJob = await artifactsForJobs(api, jobs);
  const registryVersions =
    fulfilledValue<{ versions: RegistryVersion[] }>(registryResult)?.versions ?? [];
  const apiWarnings = [
    rejectedMessage(jobsResult),
    rejectedMessage(registryResult),
    ...Object.values(artifactsByJob)
      .map((item) => item.error)
      .filter((message): message is string => Boolean(message)),
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
          Portal pages call the configured API/BFF for request intake, metadata design chat,
          draft artifacts, validation evidence, blockers, and previous analysis history.
        </p>
        <div className="form-actions">
          <Link className="primary-action" href="/requests/new">
            Create PPM request
          </Link>
          <Link className="secondary-action" href="/jobs">
            View all analysis history
          </Link>
          <Link className="secondary-action" href="/metadata/search">
            Search metadata
          </Link>
        </div>
      </section>

      <section className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Recent analyses</p>
              <h2>{jobs.length > 0 ? `${jobs.length} latest jobs` : "No jobs returned"}</h2>
            </div>
          </div>
          {jobs.length > 0 ? (
            <div className="stack">
              <AnalysisHistoryList jobs={jobs} artifactsByJob={artifactsByJob} compact />
              <Link href="/jobs">View all analysis history</Link>
            </div>
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
              <p className="eyebrow">Metadata design</p>
              <h2>Table previews</h2>
            </div>
            <StatusPill value="CHAT" label="design-run" />
          </div>
          <p className="lede">
            Ask for a new table design or refine the current draft with read-only metadata
            evidence.
          </p>
          <Link href="/metadata/design">Open metadata design chat</Link>
        </div>
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
