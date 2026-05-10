import { DependencyBlocker } from "@/components/dependency-blocker";
import { JobStatusView } from "@/components/job-status-view";
import { getPortalApi } from "@/lib/api/client";
import type { PortalApi } from "@/lib/api/portal-api";
import type { ArtifactSummary, Job } from "@/lib/api/types";
import { jobStatusSummary } from "@/lib/presentation";

export const dynamic = "force-dynamic";

export default async function JobPage({
  params,
}: Readonly<{
  params: Promise<{ jobId: string }>;
}>) {
  const { jobId } = await params;
  let api: PortalApi;
  try {
    api = getPortalApi();
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Portal API is not configured"
          message={error instanceof Error ? error.message : "PORTAL_API_BASE_URL is required."}
        />
      </div>
    );
  }
  let job: Job;
  let artifactResponse: { jobId: string; artifacts: ArtifactSummary[] };
  try {
    [job, artifactResponse] = await Promise.all([
      api.getJob(jobId),
      api.listJobArtifacts(jobId),
    ]);
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Job dependency is unavailable"
          message={error instanceof Error ? error.message : "PLF workflow repository is required."}
          code="P21_JOB_DEPENDENCY_BLOCKED"
        />
      </div>
    );
  }

  return (
    <JobStatusView
      job={job}
      scenarioSummary={jobStatusSummary(job.status)}
      artifacts={artifactResponse.artifacts}
    />
  );
}
