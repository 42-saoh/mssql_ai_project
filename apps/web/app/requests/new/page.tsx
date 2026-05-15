import { redirect } from "next/navigation";
import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { RequestForm } from "@/components/request-form";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type {
  MetadataProfile,
  RequestedOutputType,
  TargetObjectType,
} from "@/lib/api/types";
import { getPilotManifestSummary } from "@/lib/pilot-manifest";

export const dynamic = "force-dynamic";

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

async function submitRequest(formData: FormData) {
  "use server";

  const outputs = formData.getAll("outputs").map(String) as RequestedOutputType[];
  const api = getPortalApi();
  const response = await api.createSPAnalysisRequest({
    dbProfileId: String(formData.get("dbProfileId") ?? "ppm"),
    target: {
      type: String(formData.get("targetType") ?? "PROCEDURE") as TargetObjectType,
      schema: String(formData.get("schema") ?? "dbo"),
      name: String(formData.get("name") ?? ""),
    },
    outputs: outputs.length > 0 ? outputs : ["SP_ANALYSIS_DOCUMENT"],
    options: {
      includeEvidenceRefs: formData.get("includeEvidenceRefs") === "on",
      includeModernizationHints: formData.get("includeModernizationHints") === "on",
      useLlmAnalysis: formData.get("useLlmAnalysis") === "on",
      llmProfileId: String(formData.get("llmProfileId") ?? "openai_sp_semantic_analysis") as
        | "openai_sp_semantic_analysis"
        | "openai_fast_test",
      allowSpDefinitionToModel: formData.get("allowSpDefinitionToModel") === "on",
      sourceContextMode: String(formData.get("sourceContextMode") ?? "RETRIEVED_SPANS") as
        | "NONE"
        | "RETRIEVED_SPANS",
      sourceDependencyMode: String(
        formData.get("sourceDependencyMode") ?? "CONFIRMED_PROCEDURES",
      ) as "NONE" | "CONFIRMED_PROCEDURES",
      useAiToolOrchestration: formData.get("useAiToolOrchestration") === "on",
      usePlatformToolOrchestration:
        formData.get("usePlatformToolOrchestration") === "on",
    },
  });
  redirect(`/jobs/${response.jobId}`);
}

function requestOptionsFromForm(formData: FormData) {
  return {
    includeEvidenceRefs: formData.get("includeEvidenceRefs") === "on",
    includeModernizationHints: formData.get("includeModernizationHints") === "on",
    useLlmAnalysis: formData.get("useLlmAnalysis") === "on",
    llmProfileId: String(formData.get("llmProfileId") ?? "openai_sp_semantic_analysis") as
      | "openai_sp_semantic_analysis"
      | "openai_fast_test",
    allowSpDefinitionToModel: formData.get("allowSpDefinitionToModel") === "on",
    sourceContextMode: String(formData.get("sourceContextMode") ?? "RETRIEVED_SPANS") as
      | "NONE"
      | "RETRIEVED_SPANS",
    sourceDependencyMode: String(
      formData.get("sourceDependencyMode") ?? "CONFIRMED_PROCEDURES",
    ) as "NONE" | "CONFIRMED_PROCEDURES",
    useAiToolOrchestration: formData.get("useAiToolOrchestration") === "on",
    usePlatformToolOrchestration:
      formData.get("usePlatformToolOrchestration") === "on",
  };
}

async function submitBatchRequest(formData: FormData) {
  "use server";

  const outputs = formData.getAll("outputs").map(String) as RequestedOutputType[];
  const targets = String(formData.get("batchTargets") ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [schema = "dbo", name = ""] = line.includes(".")
        ? line.split(".", 2)
        : ["dbo", line];
      return {
        type: "PROCEDURE" as TargetObjectType,
        schema: schema.trim() || "dbo",
        name: name.trim(),
      };
    })
    .filter((target) => target.name);
  const api = getPortalApi();
  const response = await api.createSPAnalysisBatchRequest({
    dbProfileId: String(formData.get("dbProfileId") ?? "ppm"),
    targets,
    outputs: outputs.length > 0 ? outputs : ["SP_ANALYSIS_DOCUMENT"],
    options: requestOptionsFromForm(formData),
  });
  const params = new URLSearchParams({
    batchId: response.batchId,
    batchStatus: response.status,
    batchLimits: `${response.limits.maxTargets ?? 0}/${response.limits.maxConcurrentJobs ?? 0}`,
  });
  if (response.accepted.length > 0) {
    params.set(
      "batchJobs",
      response.accepted
        .map((item) => `${item.jobId}:${item.target.schema}.${item.target.name}`)
        .join(","),
    );
  }
  if (response.rejected.length > 0) {
    params.set(
      "batchRejected",
      response.rejected
        .map((item) => `${item.code}:${item.target.schema}.${item.target.name}`)
        .join(","),
    );
  }
  redirect(`/requests/new?${params.toString()}`);
}

export default async function NewRequestPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
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
  let profileResponse: { defaultProfileId: string; profiles: MetadataProfile[] };
  let params: Record<string, string | string[] | undefined>;
  try {
    [profileResponse, params] = await Promise.all([api.listMetadataProfiles(), searchParams]);
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Metadata profiles are unavailable"
          message={formatPortalApiError(error, "PLF/PPM prerequisites are missing.")}
          code={portalApiErrorCode(error, "P21_PORTAL_METADATA_PROFILES_BLOCKED")}
        />
      </div>
    );
  }
  const pilotManifest = getPilotManifestSummary();
  const requestedSampleId = firstParam(params.sample);
  const selectedSample =
    pilotManifest.procedureSamples.find((sample) => sample.id === requestedSampleId) ??
    pilotManifest.procedureSamples[0];
  const batchStatus = firstParam(params.batchStatus);
  const batchId = firstParam(params.batchId);
  const batchJobs = (firstParam(params.batchJobs) ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [jobId, target] = item.split(":", 2);
      return { jobId, target };
    });
  const batchRejected = (firstParam(params.batchRejected) ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [code, target] = item.split(":", 2);
      return { code, target };
    });
  const batchLimits = firstParam(params.batchLimits);

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Request intake</p>
            <h1>Stored procedure analysis request</h1>
          </div>
          <span className="quiet-label">Draft only</span>
        </div>
        <p className="lede">
          Compose the OpenAPI-shaped request payload for one stored procedure target. Submission
          calls the configured API and redirects to the returned workflow job.
        </p>
      </section>

      {batchStatus ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Batch result</p>
              <h2>{batchStatus}</h2>
            </div>
            <span className="quiet-label">{batchId}</span>
          </div>
          <div className="metric-grid">
            <div>
              <span>Accepted</span>
              <strong>{batchJobs.length}</strong>
            </div>
            <div>
              <span>Rejected</span>
              <strong>{batchRejected.length}</strong>
            </div>
            <div>
              <span>Limits</span>
              <strong>{batchLimits ?? "active"}</strong>
            </div>
          </div>
          {batchJobs.length > 0 ? (
            <div className="batch-list">
              {batchJobs.map((item) => (
                <Link href={`/jobs/${item.jobId}`} key={item.jobId}>
                  {item.target} · {item.jobId}
                </Link>
              ))}
            </div>
          ) : null}
          {batchRejected.length > 0 ? (
            <div className="blocker-list">
              {batchRejected.map((item) => (
                <article className="blocker-row" key={`${item.code}-${item.target}`}>
                  <strong>{item.code}</strong>
                  <span>{item.target}</span>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="panel">
        <RequestForm
          defaultProfileId={profileResponse.defaultProfileId}
          profiles={profileResponse.profiles}
          pilotManifest={pilotManifest}
          selectedSample={selectedSample}
          action={submitRequest}
          batchAction={submitBatchRequest}
        />
      </section>
    </div>
  );
}
