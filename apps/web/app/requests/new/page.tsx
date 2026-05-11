import { redirect } from "next/navigation";
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
    },
  });
  redirect(`/jobs/${response.jobId}`);
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

      <section className="panel">
        <RequestForm
          defaultProfileId={profileResponse.defaultProfileId}
          profiles={profileResponse.profiles}
          pilotManifest={pilotManifest}
          selectedSample={selectedSample}
          action={submitRequest}
        />
      </section>
    </div>
  );
}
