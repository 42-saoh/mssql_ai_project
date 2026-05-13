import type {
  AgentRunSummary,
  Artifact,
  ArtifactSummary,
  Job,
  KnowledgeAssetSummary,
  KnowledgeAssetVersion,
  KnowledgeExportRequest,
  KnowledgeExportResponse,
  KnowledgeFactGraph,
  MetadataAnalysisRequest,
  MetadataAnalysisResponse,
  MetadataProfile,
  MetadataSearchRequest,
  MetadataSearchResponse,
  MetadataToolInvokeRequest,
  MetadataToolInvokeResponse,
  MetadataToolName,
  MetadataToolSummary,
  RegistryVersion,
  SPAnalysisBatchRequest,
  SPAnalysisBatchResponse,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
} from "./types.ts";

export interface PortalApi {
  createSPAnalysisRequest(request: SPAnalysisRequest): Promise<SubmitRequestResponse>;
  createSPAnalysisBatchRequest(
    request: SPAnalysisBatchRequest,
  ): Promise<SPAnalysisBatchResponse>;
  listJobs(limit?: number): Promise<{ jobs: Job[] }>;
  getJob(jobId: string): Promise<Job>;
  listJobAgentRuns(
    jobId: string,
    limit?: number,
  ): Promise<{ jobId: string; agentRuns: AgentRunSummary[] }>;
  listJobArtifacts(jobId: string): Promise<{ jobId: string; artifacts: ArtifactSummary[] }>;
  listJobKnowledgeAssets(
    jobId: string,
  ): Promise<{ jobId: string; knowledgeAssets: KnowledgeAssetSummary[] }>;
  getKnowledgeAsset(assetId: string): Promise<KnowledgeAssetSummary>;
  listKnowledgeAssetVersions(
    assetId: string,
  ): Promise<{ assetId: string; versions: KnowledgeAssetVersion[] }>;
  listKnowledgeFacts(assetId: string, versionId: string): Promise<KnowledgeFactGraph>;
  createKnowledgeExport(request: KnowledgeExportRequest): Promise<KnowledgeExportResponse>;
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
  analyzeMetadata(request: MetadataAnalysisRequest): Promise<MetadataAnalysisResponse>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
