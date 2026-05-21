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
  { params }: Readonly<{ params: Promise<{ conversationId: string }> }>,
) {
  const { conversationId } = await params;
  try {
    const api = getPortalApi();
    const conversation = await api.getMetadataDesignConversation(conversationId);
    return NextResponse.json(conversation);
  } catch (error) {
    const status = error instanceof PortalApiHttpError ? error.status : 500;
    return NextResponse.json(
      {
        code: portalApiErrorCode(error, "METADATA_DESIGN_CONVERSATION_BLOCKED"),
        message: formatPortalApiError(error, "Metadata design conversation could not be read."),
      },
      { status },
    );
  }
}
