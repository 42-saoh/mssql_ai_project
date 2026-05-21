import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import { artifactFilename, sanitizeFilePart } from "@/lib/artifact-download";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";
import type { Artifact } from "@/lib/api/types";
import { displayArtifactContent, displayCaveatText } from "@/lib/display-caveats";
import { createStoreOnlyZip, type ZipEntry } from "@/lib/zip-writer";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: Readonly<{ params: Promise<{ jobId: string }> }>,
) {
  const { jobId } = await params;
  try {
    const api = getPortalApi();
    const listed = await api.listJobArtifacts(jobId);
    const artifacts = await Promise.all(
      listed.artifacts.map((artifact) => api.getArtifact(artifact.artifactId)),
    );
    const entries = artifactZipEntries(jobId, artifacts);
    const zip = createStoreOnlyZip(entries);
    const filename = `${sanitizeFilePart(jobId)}-draft-artifacts.zip`;
    return new Response(zip, {
      headers: {
        "cache-control": "no-store",
        "content-disposition": `attachment; filename="${filename}"`,
        "content-type": "application/zip",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "P35_ARTIFACT_BUNDLE_DOWNLOAD_BLOCKED"),
        message: formatPortalApiError(error, "Draft artifact bundle could not be downloaded."),
      },
      { status },
    );
  }
}

function artifactZipEntries(jobId: string, artifacts: Artifact[]): ZipEntry[] {
  const manifest = {
    jobId,
    generatedAt: new Date().toISOString(),
    draftOnly: true,
    artifacts: artifacts.map((artifact, index) => ({
      artifactId: artifact.artifactId,
      type: artifact.type,
      status: artifact.status,
      title: artifact.title ?? null,
      targetKey: artifact.targetKey ?? null,
      filename: artifactFilename(artifact, index + 1),
      evidenceCoverage: artifact.evidenceCoverage ?? null,
      caveats: (artifact.caveats ?? []).map(displayCaveatText),
    })),
  };
  return [
    {
      name: "README.md",
      content: [
        `# Draft artifacts for ${jobId}`,
        "",
        "These files are draft outputs from the MSSQL Agent Portal.",
        "They contain sanitized draft artifact contents for offline reading and handoff.",
        "",
      ].join("\n"),
    },
    {
      name: "manifest.json",
      content: JSON.stringify(manifest, null, 2),
    },
    ...artifacts.map((artifact, index) => ({
      name: artifactFilename(artifact, index + 1),
      content: displayArtifactContent(artifact.content),
    })),
  ];
}
