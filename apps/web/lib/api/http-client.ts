import type { PortalApi } from "./portal-api";
import type { ApprovalDecisionRequest, MetadataSearchRequest, SPAnalysisRequest } from "./types";

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
    throw new Error(`Portal API request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

export function createHttpPortalApi({ baseUrl, fetcher = fetch }: HttpPortalApiOptions): PortalApi {
  return {
    createSPAnalysisRequest(request: SPAnalysisRequest) {
      return readJson(fetcher, baseUrl, "/api/v1/requests/sp-analysis", {
        method: "POST",
        json: request,
      });
    },

    getJob(jobId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/jobs/${encodeURIComponent(jobId)}`);
    },

    listJobArtifacts(jobId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts`);
    },

    getArtifact(artifactId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/artifacts/${encodeURIComponent(artifactId)}`);
    },

    validateArtifact(artifactId: string) {
      return readJson(fetcher, baseUrl, `/api/v1/artifacts/${encodeURIComponent(artifactId)}/validation`, {
        method: "POST",
      });
    },

    createApprovalDecision(artifactId: string, request: ApprovalDecisionRequest) {
      return readJson(
        fetcher,
        baseUrl,
        `/api/v1/artifacts/${encodeURIComponent(artifactId)}/approval-decisions`,
        {
          method: "POST",
          json: request,
        },
      );
    },

    listMetadataProfiles() {
      return readJson(fetcher, baseUrl, "/api/v1/metadata/db-profiles");
    },

    searchMetadataObjects(request: MetadataSearchRequest) {
      const params = new URLSearchParams({
        dbProfileId: request.dbProfileId,
        query: request.query,
      });

      if (request.limit !== undefined) {
        params.set("limit", String(request.limit));
      }

      for (const objectType of request.objectTypes ?? []) {
        params.append("objectTypes", objectType);
      }

      return readJson(fetcher, baseUrl, `/api/v1/metadata/search?${params.toString()}`);
    },

    listRegistryVersions() {
      return readJson(fetcher, baseUrl, "/api/v1/registry/versions");
    },
  };
}
