import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";
import type { MetadataDesignRunRequest } from "@/lib/api/types";
import { DEFAULT_METADATA_PROFILE } from "@/lib/metadata-design/constants";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const payload = normalizeRequest((await request.json()) as MetadataDesignRunRequest);
    const api = getPortalApi();
    const run = await api.submitMetadataDesignRun(payload);
    return NextResponse.json(run, { status: 202 });
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "METADATA_DESIGN_RUN_BLOCKED"),
        message: formatPortalApiError(error, "Metadata design run could not start."),
      },
      { status },
    );
  }
}

function normalizeRequest(request: MetadataDesignRunRequest): MetadataDesignRunRequest {
  const maxCandidates = clampMaxCandidates(Number(request.options?.maxCandidates ?? 5));
  const designInputs = request.designInputs ?? {};
  const tableNameHint =
    typeof designInputs.tableNameHint === "string" ? designInputs.tableNameHint.trim() : "";
  return {
    ...request,
    dbProfileId: DEFAULT_METADATA_PROFILE,
    designInputs: {
      fields: [],
      ...designInputs,
      tableNameHint: tableNameHint || undefined,
    },
    options: {
      ...request.options,
      useLlmAnalysis: request.options?.useLlmAnalysis ?? true,
      useAiToolOrchestration: request.options?.useAiToolOrchestration ?? true,
      llmProfileId: request.options?.llmProfileId ?? "openai_sp_semantic_analysis",
      maxCandidates,
      generateDtoDraft: request.options?.generateDtoDraft ?? true,
      conversationMode: request.options?.conversationMode ?? "NEW_DESIGN",
    },
  };
}

function clampMaxCandidates(value: number): number {
  if (!Number.isFinite(value)) {
    return 5;
  }
  return Math.min(Math.max(Math.trunc(value), 1), 10);
}
