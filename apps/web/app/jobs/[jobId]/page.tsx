import { JobStatusView } from "@/components/job-status-view";
import { getPortalApi } from "@/lib/api/client";
import { jobStatusSummary } from "@/lib/presentation";

export default async function JobPage({
  params,
}: Readonly<{
  params: Promise<{ jobId: string }>;
}>) {
  const { jobId } = await params;
  const api = getPortalApi();
  const [job, artifactResponse] = await Promise.all([
    api.getJob(jobId),
    api.listJobArtifacts(jobId),
  ]);

  return (
    <JobStatusView
      job={job}
      scenarioSummary={jobStatusSummary(job.status)}
      artifacts={artifactResponse.artifacts}
    />
  );
}
