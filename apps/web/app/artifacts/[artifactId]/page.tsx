import { redirect } from "next/navigation";
import { ArtifactPreview } from "@/components/artifact-preview";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { getPortalApi } from "@/lib/api/client";
import type { PortalApi } from "@/lib/api/portal-api";

export const dynamic = "force-dynamic";

async function runValidation(formData: FormData) {
  "use server";

  const artifactId = String(formData.get("artifactId") ?? "");
  const api = getPortalApi();
  await api.validateArtifact(artifactId);
  redirect(`/artifacts/${artifactId}`);
}

export default async function ArtifactPage({
  params,
}: Readonly<{
  params: Promise<{ artifactId: string }>;
}>) {
  const { artifactId } = await params;
  let api: PortalApi;
  try {
    api = getPortalApi();
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Portal API is not configured"
          message={error instanceof Error ? error.message : "PORTAL_API_BASE_URL is required."}
        />
      </div>
    );
  }

  const [artifactResult, validationResult] = await Promise.allSettled([
    api.getArtifact(artifactId),
    api.getLatestValidation(artifactId),
  ]);

  if (artifactResult.status === "rejected") {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Artifact dependency is unavailable"
          message={
            artifactResult.reason instanceof Error
              ? artifactResult.reason.message
              : "PLF artifact repository is required."
          }
          code="P21_ARTIFACT_DEPENDENCY_BLOCKED"
        />
      </div>
    );
  }

  const validation = validationResult.status === "fulfilled" ? validationResult.value : null;
  return (
    <ArtifactPreview
      artifact={artifactResult.value}
      validation={validation}
      validateAction={runValidation}
    />
  );
}
