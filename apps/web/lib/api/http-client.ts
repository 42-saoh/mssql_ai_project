import { readPortalApiError } from "./errors.ts";
import type { PortalApi } from "./portal-api.ts";
import type {
  MetadataAnalysisRequest,
  MetadataDesignRunRequest,
  KnowledgeExportRequest,
  MetadataToolInvokeRequest,
  MetadataToolName,
  SPAnalysisBatchRequest,
  SPAnalysisRequest,
} from "./types.ts";

interface HttpPortalApiOptions {
  baseUrl: string;
  fetcher?: typeof fetch;
}

async function readJson<T>(
  fetcher: typeof fetch,
  baseUrl: string,
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const headers = new Headers(init?.headers);

  let body = init?.body;
  if (init?.json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(init.json);
  }

  const response = await fetcher(new URL(path, baseUrl), {
    ...init,
    headers,
    body,
  });

  if (!response.ok) {
    const error = await readPortalApiError(response, path);
    throw error;
  }

  return (await response.json()) as T;
}

export function createHttpPortalApi({ baseUrl, fetcher = fetch }: HttpPortalApiOptions): PortalApi {
  return {
    createSPAnalysisRequest(request: SPAnalysisRequest, options?: { runAsync?: boolean }) {
      const params = new URLSearchParams();
      if (options?.runAsync) {
        params.set("runAsync", "true");
      }
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return readJson(fetcher, baseUrl, `/api/v1/requests/sp-analysis${suffix}`, {
        method: "POST",
        json: request,
      });
    },

    createSPAnalysisBatchRequest(request: SPAnalysisBatchRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/requests/sp-analysis/batch", {
        method: "POST",
        json: request,
      });
    },

    listJobs(limit?: number, targetKey?: string) {
      const params = new URLSearchParams();
      if (limit !== undefined) {
        params.set("limit", String(limit));
      }
      if (targetKey) {
        params.set("targetKey", targetKey);
      }
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return readJson(fetcher, baseUrl, `/api/v1/jobs${suffix}`);
    },

    getJob(jobId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/jobs/${encodeURIComponent(jobId)}`);
    },

    listJobAgentRuns(jobId: string, limit?: number) {
      const params = new URLSearchParams();
      if (limit !== undefined) {
        params.set("limit", String(limit));
      }
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/jobs/${encodeURIComponent(jobId)}/agent-runs${suffix}`,
      );
    },

    listJobArtifacts(jobId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts`);
    },

    listJobKnowledgeAssets(jobId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/jobs/${encodeURIComponent(jobId)}/knowledge-assets`,
      );
    },

    getKnowledgeAsset(assetId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/knowledge/assets/${encodeURIComponent(assetId)}`,
      );
    },

    listKnowledgeAssetVersions(assetId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/knowledge/assets/${encodeURIComponent(assetId)}/versions`,
      );
    },

    listKnowledgeFacts(assetId: string, versionId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/knowledge/assets/${encodeURIComponent(assetId)}/versions/${encodeURIComponent(
          versionId,
        )}/facts`,
      );
    },

    createKnowledgeExport(request: KnowledgeExportRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/knowledge/exports", {
        method: "POST",
        json: request,
      });
    },

    getArtifact(artifactId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/artifacts/${encodeURIComponent(artifactId)}`);
    },

    getLatestValidation(artifactId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/artifacts/${encodeURIComponent(artifactId)}/validation/latest`,
      );
    },

    validateArtifact(artifactId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/artifacts/${encodeURIComponent(artifactId)}/validation`,
        {
          method: "POST",
        },
      );
    },

    listMetadataProfiles() {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/db-profiles");
    },

    listMetadataTools() {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/tools");
    },

    invokeMetadataTool(toolName: MetadataToolName, request: MetadataToolInvokeRequest) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/metadata/tools/${encodeURIComponent(toolName)}/invoke`,
        {
          method: "POST",
          json: request,
        },
      );
    },

    analyzeMetadata(request: MetadataAnalysisRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/analyze", {
        method: "POST",
        json: request,
      });
    },

    submitMetadataAnalysisRun(request: MetadataAnalysisRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/analysis-runs", {
        method: "POST",
        json: request,
      });
    },

    getMetadataAnalysisRun(runId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/metadata/analysis-runs/${encodeURIComponent(runId)}`,
      );
    },

    submitMetadataDesignRun(request: MetadataDesignRunRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/design-runs", {
        method: "POST",
        json: request,
      });
    },

    getMetadataDesignRun(runId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/metadata/design-runs/${encodeURIComponent(runId)}`,
      );
    },

    getMetadataDesignConversation(conversationId: string) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/metadata/design-conversations/${encodeURIComponent(conversationId)}`,
      );
    },

    listRegistryVersions() {
      return readJson(fetcher, baseUrl, "/api/v1/registry/versions");
    },
  };
}
