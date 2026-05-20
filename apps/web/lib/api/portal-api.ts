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
  MetadataAnalysisRunStatus,
  MetadataDesignConversation,
  MetadataDesignRunRequest,
  MetadataDesignRunStatus,
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
  createSPAnalysisRequest(
    request: SPAnalysisRequest,
    options?: { runAsync?: boolean },
  ): Promise<SubmitRequestResponse>;
  createSPAnalysisBatchRequest(
    request: SPAnalysisBatchRequest,
  ): Promise<SPAnalysisBatchResponse>;
  listJobs(limit?: number, targetKey?: string): Promise<{ jobs: Job[] }>;
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
  analyzeMetadata(request: MetadataAnalysisRequest): Promise<MetadataAnalysisResponse>;
  searchMetadataObjects(request: MetadataSearchRequest): Promise<MetadataSearchResponse>;
  submitMetadataAnalysisRun(request: MetadataAnalysisRequest): Promise<MetadataAnalysisRunStatus>;
  getMetadataAnalysisRun(runId: string): Promise<MetadataAnalysisRunStatus>;
  submitMetadataDesignRun(request: MetadataDesignRunRequest): Promise<MetadataDesignRunStatus>;
  getMetadataDesignRun(runId: string): Promise<MetadataDesignRunStatus>;
  getMetadataDesignConversation(conversationId: string): Promise<MetadataDesignConversation>;
  listRegistryVersions(): Promise<{ versions: RegistryVersion[] }>;
}
