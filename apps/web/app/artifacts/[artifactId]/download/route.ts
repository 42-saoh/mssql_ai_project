import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import { artifactContentType, artifactFilename } from "@/lib/artifact-download";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: Readonly<{ params: Promise<{ artifactId: string }> }>,
) {
  const { artifactId } = await params;
  try {
    const api = getPortalApi();
    const artifact = await api.getArtifact(artifactId);
    const filename = artifactFilename(artifact);
    return new Response(artifact.content, {
      headers: {
        "cache-control": "no-store",
        "content-disposition": `attachment; filename="${filename}"`,
        "content-type": artifactContentType(artifact.type),
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "P35_ARTIFACT_DOWNLOAD_BLOCKED"),
        message: formatPortalApiError(error, "Draft artifact could not be downloaded."),
      },
      { status },
    );
  }
}
