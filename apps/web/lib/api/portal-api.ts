import type {
  AgentRunSummary,
  Artifact,
  ArtifactSummary,
  Job,
  MetadataProfile,
  MetadataSearchRequest,
  MetadataSearchResponse,
  RegistryVersion,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
} from "./types.ts";

export interface PortalApi {
  createSPAnalysisRequest(request: SPAnalysisRequest): Promise<SubmitRequestResponse>;
  listJobs(limit?: number): Promise<{ jobs: Job[] }>;
  getJob(jobId: string): Promise<Job>;
  listJobAgentRuns(
    jobId: string,
    limit?: number,
  ): Promise<{ jobId: string; agentRuns: AgentRunSummary[] }>;
  listJobArtifacts(jobId: string): Promise<{ jobId: string; artifacts: ArtifactSummary[] }>;
  getArtifact(artifactId: string): Promise<Artifact>;
  getLatestValidation(artifactId: string): Promise<ValidationReport>;
  validateArtifact(artifactId: string): Promise<ValidationReport>;
  listMetadataProfiles(): Promise<{ defaultProfileId: string; profiles: MetadataProfile[] }>;
  searchMetadataObjects(request: MetadataSearchRequest): Promise<MetadataSearchResponse>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
