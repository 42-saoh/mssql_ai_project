import { createHttpPortalApi } from "./http-client";
import type { PortalApi } from "./portal-api";

export function getPortalApi(): PortalApi {
  const apiMode = process.env.PORTAL_API_MODE ?? "http";

  if (apiMode !== "http") {
    throw new Error("PORTAL_API_MODE must be http for the P21 no-mock portal.");
  }

  const baseUrl = process.env.PORTAL_API_BASE_URL;

  if (!baseUrl) {
    throw new Error("PORTAL_API_BASE_URL is required for the P21 no-mock portal.");
  }

  return createHttpPortalApi({ baseUrl });
}
