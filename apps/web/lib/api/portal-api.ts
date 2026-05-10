import type {
  Artifact,
  ArtifactSummary,
  ApprovalDecisionRequest,
  ApprovalRecord,
  Job,
  MetadataProfile,
  MetadataSearchRequest,
  MetadataSearchResponse,
  RegistryVersion,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
} from "./types";

export interface PortalApi {
  createSPAnalysisRequest(request: SPAnalysisRequest): Promise<SubmitRequestResponse>;
  listJobs(limit?: number): Promise<{ jobs: Job[] }>;
  getJob(jobId: string): Promise<Job>;
  listJobArtifacts(jobId: string): Promise<{ jobId: string; artifacts: ArtifactSummary[] }>;
  getArtifact(artifactId: string): Promise<Artifact>;
  getLatestValidation(artifactId: string): Promise<ValidationReport>;
  validateArtifact(artifactId: string): Promise<ValidationReport>;
  createApprovalDecision(
    artifactId: string,
    request: ApprovalDecisionRequest,
  ): Promise<ApprovalRecord>;
  listMetadataProfiles(): Promise<{ defaultProfileId: string; profiles: MetadataProfile[] }>;
  searchMetadataObjects(request: MetadataSearchRequest): Promise<MetadataSearchResponse>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
