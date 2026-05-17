import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";
import type { MetadataAnalysisRequest } from "@/lib/api/types";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const payload = normalizeRequest((await request.json()) as MetadataAnalysisRequest);
    const api = getPortalApi();
    const run = await api.submitMetadataAnalysisRun(payload);
    return NextResponse.json(run, { status: 202 });
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "AI_METADATA_ANALYSIS_RUN_BLOCKED"),
        message: formatPortalApiError(error, "Metadata analysis run could not start."),
      },
      { status },
    );
  }
}

function normalizeRequest(request: MetadataAnalysisRequest): MetadataAnalysisRequest {
  const maxTargets = clampMaxTargets(Number(request.options?.maxTargets ?? 1));
  return {
    ...request,
    options: {
      ...request.options,
      useLlmAnalysis: request.options?.useLlmAnalysis ?? true,
      useAiToolOrchestration: request.options?.useAiToolOrchestration ?? true,
      llmProfileId: request.options?.llmProfileId ?? "openai_sp_semantic_analysis",
      maxTargets,
      generateDtoDrafts: request.options?.generateDtoDrafts ?? false,
    },
  };
}

function clampMaxTargets(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(Math.max(Math.trunc(value), 1), 5);
}
