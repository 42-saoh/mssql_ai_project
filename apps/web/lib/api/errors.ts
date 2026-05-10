interface PortalApiHttpErrorOptions {
  status: number;
  statusText: string;
  path: string;
  code: string | undefined;
  detail: string | undefined;
}

export class PortalApiHttpError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly path: string;
  readonly code: string | undefined;
  readonly detail: string;

  constructor({ status, statusText, path, code, detail }: PortalApiHttpErrorOptions) {
    const safeDetail = detail?.trim() || `HTTP ${status} ${statusText}`;
    const message = code ? `${code}: ${safeDetail}` : safeDetail;

    super(message);
    this.name = "PortalApiHttpError";
    this.status = status;
    this.statusText = statusText;
    this.path = path;
    this.code = code;
    this.detail = safeDetail;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function safeDetail(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return "Request validation failed; API returned structured validation details.";
  }

  if (isRecord(value)) {
    return "Request failed; API returned structured error details.";
  }

  return undefined;
}

export async function readPortalApiError(
  response: Response,
  path: string,
): Promise<PortalApiHttpError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  const code = isRecord(payload) ? safeString(payload.code) : undefined;
  const detail = isRecord(payload) ? safeDetail(payload.detail) : undefined;

  return new PortalApiHttpError({
    status: response.status,
    statusText: response.statusText,
    path,
    code,
    detail,
  });
}

export function formatPortalApiError(error: unknown, fallback: string): string {
  if (error instanceof PortalApiHttpError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export function portalApiErrorCode(error: unknown, fallback: string): string {
  return error instanceof PortalApiHttpError && error.code ? error.code : fallback;
}
