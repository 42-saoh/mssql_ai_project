import { NextResponse } from "next/server";
import { getPortalApi } from "@/lib/api/client";
import {
  PortalApiHttpError,
  formatPortalApiError,
  portalApiErrorCode,
} from "@/lib/api/errors";
import type { MetadataDesignRunRequest } from "@/lib/api/types";

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
  return {
    ...request,
    designInputs: {
      fields: [],
      ...request.designInputs,
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
