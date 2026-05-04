import type {
  Artifact,
  ArtifactSummary,
  ApprovalDecisionRequest,
  ApprovalRecord,
  Job,
  MetadataProfile,
  RegistryVersion,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
} from "./types";

export interface PortalApi {
  createSPAnalysisRequest(request: SPAnalysisRequest): Promise<SubmitRequestResponse>;
  getJob(jobId: string): Promise<Job>;
  listJobArtifacts(jobId: string): Promise<{ jobId: string; artifacts: ArtifactSummary[] }>;
  getArtifact(artifactId: string): Promise<Artifact>;
  validateArtifact(artifactId: string): Promise<ValidationReport>;
  createApprovalDecision(
    artifactId: string,
    request: ApprovalDecisionRequest,
  ): Promise<ApprovalRecord>;
  listMetadataProfiles(): Promise<{ defaultProfileId: string; profiles: MetadataProfile[] }>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
