import { createHttpPortalApi } from "./http-client";
import { createMockPortalApi } from "./mock-adapter";
import type { PortalApi } from "./portal-api";

export function getPortalApi(): PortalApi {
  const apiMode = process.env.PORTAL_API_MODE ?? "mock";

  if (apiMode === "http") {
    const baseUrl = process.env.PORTAL_API_BASE_URL;

    if (!baseUrl) {
      throw new Error("PORTAL_API_BASE_URL is required when PORTAL_API_MODE=http");
    }

    return createHttpPortalApi({ baseUrl });
  }

  return createMockPortalApi();
}
