import type {
  AgentRunSummary,
  Artifact,
  ArtifactSummary,
  Job,
  MetadataProfile,
  MetadataSearchRequest,
  MetadataSearchResponse,
  MetadataToolInvokeRequest,
  MetadataToolInvokeResponse,
  MetadataToolName,
  MetadataToolSummary,
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
  listMetadataTools(): Promise<{ tools: MetadataToolSummary[] }>;
  invokeMetadataTool(
    toolName: MetadataToolName,
    request: MetadataToolInvokeRequest,
  ): Promise<MetadataToolInvokeResponse>;
  searchMetadataObjects(request: MetadataSearchRequest): Promise<MetadataSearchResponse>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
