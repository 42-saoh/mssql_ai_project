import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const dbProfileId = params.get("dbProfileId")?.trim() || "ppm";
  const query = params.get("query")?.trim() || "";
  const limit = clampLimit(Number(params.get("limit") ?? 20));

  try {
    const api = getPortalApi();
    const response = await api.searchProcedures({ dbProfileId, query, limit });
    return NextResponse.json(response);
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "PROCEDURE_SEARCH_BLOCKED"),
        message: formatPortalApiError(error, "Procedure search could not run."),
      },
      { status },
    );
  }
}

function clampLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return 20;
  }
  return Math.min(Math.max(Math.trunc(value), 1), 100);
}
