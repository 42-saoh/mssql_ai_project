import { ArtifactPreview } from "@/components/artifact-preview";
import { getPortalApi } from "@/lib/api/client";

export default async function ArtifactPage({
  params,
}: Readonly<{
  params: Promise<{ artifactId: string }>;
}>) {
  const { artifactId } = await params;
  const api = getPortalApi();
  const [artifact, validation] = await Promise.all([
    api.getArtifact(artifactId),
    api.validateArtifact(artifactId),
  ]);

  return <ArtifactPreview artifact={artifact} validation={validation} />;
}
