import { DependencyBlocker } from "@/components/dependency-blocker";
import { JobStatusView } from "@/components/job-status-view";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { AgentRunSummary, ArtifactSummary, Job, KnowledgeAssetSummary } from "@/lib/api/types";
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
          message={formatPortalApiError(error, "PORTAL_API_BASE_URL is required.")}
        />
      </div>
    );
  }
  let job: Job;
  let artifactResponse: { jobId: string; artifacts: ArtifactSummary[] };
  let agentRunResponse: { jobId: string; agentRuns: AgentRunSummary[] };
  let knowledgeResponse: { jobId: string; knowledgeAssets: KnowledgeAssetSummary[] };
  try {
    [job, artifactResponse, agentRunResponse, knowledgeResponse] = await Promise.all([
      api.getJob(jobId),
      api.listJobArtifacts(jobId),
      api.listJobAgentRuns(jobId),
      api.listJobKnowledgeAssets(jobId),
    ]);
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Job dependency is unavailable"
          message={formatPortalApiError(error, "PLF workflow repository is required.")}
          code={portalApiErrorCode(error, "P21_JOB_DEPENDENCY_BLOCKED")}
        />
      </div>
    );
  }

  return (
    <JobStatusView
      job={job}
      scenarioSummary={jobStatusSummary(job.status)}
      artifacts={artifactResponse.artifacts}
      agentRuns={agentRunResponse.agentRuns}
      knowledgeAssets={knowledgeResponse.knowledgeAssets}
    />
  );
}
