import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: Readonly<{ params: Promise<{ runId: string }> }>,
) {
  const { runId } = await params;
  try {
    const api = getPortalApi();
    const run = await api.getMetadataDesignRun(runId);
    return NextResponse.json(run);
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "METADATA_DESIGN_RUN_BLOCKED"),
        message: formatPortalApiError(error, "Metadata design run could not be read."),
      },
      { status },
    );
  }
}
