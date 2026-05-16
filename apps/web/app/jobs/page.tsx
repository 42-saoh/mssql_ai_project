import Link from "next/link";
import {
  AnalysisHistoryList,
  type JobArtifactLookup,
  targetLabel,
} from "@/components/analysis-history-list";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { ArtifactSummary, Job, JobStatus, RequestedOutputType } from "@/lib/api/types";
import { jobStatusLabels, outputLabels } from "@/lib/presentation";

export const dynamic = "force-dynamic";

const statusOptions: JobStatus[] = [
  "SUBMITTED",
  "COLLECTING_METADATA",
  "ANALYZING",
  "GENERATING",
  "VALIDATING",
  "VALIDATION_COMPLETE",
  "FAILED",
  "CANCELED",
];

const outputOptions: RequestedOutputType[] = [
  "SP_ANALYSIS_DOCUMENT",
  "DEPENDENCY_REPORT",
  "TABLE_COLUMN_METADATA",
  "JAVA_MYBATIS_DRAFT",
  "DTO_MODEL_DRAFT",
  "DDL_DRAFT",
];

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function limitParam(value: string | string[] | undefined): number {
  const parsed = Number(firstParam(value) ?? "50");
  if (!Number.isFinite(parsed)) {
    return 50;
  }
  return Math.min(Math.max(Math.trunc(parsed), 1), 100);
}

function filterJobs(
  jobs: Job[],
  filters: {
    query: string;
    status: string;
    profile: string;
    output: string;
  },
): Job[] {
  const query = filters.query.toLowerCase();
  return jobs.filter((job) => {
    const searchable = [
      job.jobId,
      job.requestId,
      job.dbProfileId ?? "",
      targetLabel(job.target),
      ...(job.outputs ?? []),
    ]
      .join(" ")
      .toLowerCase();
    return (
      (!query || searchable.includes(query)) &&
      (!filters.status || job.status === filters.status) &&
      (!filters.profile || job.dbProfileId === filters.profile) &&
      (!filters.output || (job.outputs ?? []).includes(filters.output as RequestedOutputType))
    );
  });
}

function uniqueValues(values: (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort();
}

async function artifactsForJobs(jobs: Job[]): Promise<JobArtifactLookup> {
  const api = getPortalApi();
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
          artifacts: [] as ArtifactSummary[],
          error: formatPortalApiError(result.reason, "Artifacts unavailable."),
        },
      ];
    }),
  ) as JobArtifactLookup;
}

export default async function JobsPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
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

  const params = await searchParams;
  const limit = limitParam(params.limit);
  let jobs: Job[];
  try {
    jobs = (await api.listJobs(limit)).jobs;
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Analysis history is unavailable"
          message={formatPortalApiError(error, "PLF workflow repository is required.")}
          code={portalApiErrorCode(error, "P35_ANALYSIS_HISTORY_BLOCKED")}
        />
      </div>
    );
  }

  const filters = {
    query: firstParam(params.q)?.trim() ?? "",
    status: firstParam(params.status)?.trim() ?? "",
    profile: firstParam(params.profile)?.trim() ?? "",
    output: firstParam(params.output)?.trim() ?? "",
  };
  const filteredJobs = filterJobs(jobs, filters);
  const artifactsByJob = await artifactsForJobs(filteredJobs);
  const profiles = uniqueValues(jobs.map((job) => job.dbProfileId));

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Analysis history</p>
            <h1>Draft analysis timeline</h1>
          </div>
          <span className="quiet-label">{filteredJobs.length} shown</span>
        </div>
        <p className="lede">
          Browse previous draft analysis jobs, reopen their artifacts, and compare evidence
          caveats without exposing publish, deploy, SQL execution, or apply actions.
        </p>
        <div className="form-actions">
          <Link className="secondary-action" href="/requests/new">
            New request
          </Link>
          <Link className="secondary-action" href="/">
            Home
          </Link>
        </div>
      </section>

      <section className="panel">
        <form className="metadata-search-form" method="get">
          <div className="form-grid">
            <label>
              <span>Target or job search</span>
              <input name="q" defaultValue={filters.query} placeholder="schema.objectName" />
            </label>
            <label>
              <span>Status</span>
              <select name="status" defaultValue={filters.status}>
                <option value="">All statuses</option>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {jobStatusLabels[status]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Metadata profile</span>
              <select name="profile" defaultValue={filters.profile}>
                <option value="">All profiles</option>
                {profiles.map((profile) => (
                  <option key={profile} value={profile}>
                    {profile}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Requested output</span>
              <select name="output" defaultValue={filters.output}>
                <option value="">All outputs</option>
                {outputOptions.map((output) => (
                  <option key={output} value={output}>
                    {outputLabels[output]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Limit</span>
              <input max="100" min="1" name="limit" type="number" defaultValue={limit} />
            </label>
          </div>
          <div className="form-actions">
            <button type="submit">Filter history</button>
            <Link className="secondary-action" href="/jobs">
              Reset
            </Link>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Workflow jobs</p>
            <h2>Recent analyses</h2>
          </div>
          <span className="quiet-label">latest {limit}</span>
        </div>
        <AnalysisHistoryList jobs={filteredJobs} artifactsByJob={artifactsByJob} />
      </section>
    </div>
  );
}
