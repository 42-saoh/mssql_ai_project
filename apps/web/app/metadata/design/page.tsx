import { DependencyBlocker } from "@/components/dependency-blocker";
import {
  MetadataDesignChat,
  type MetadataDesignWorkMode,
} from "@/components/metadata-design-chat";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";

export const dynamic = "force-dynamic";

export default async function MetadataDesignPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const params = await searchParams;
  const initialWorkMode = initialWorkModeForIntent(firstParam(params.intent));
  let profiles;
  try {
    const api = getPortalApi();
    profiles = await api.listMetadataProfiles();
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Portal API is not configured"
          message={formatPortalApiError(error, "PORTAL_API_BASE_URL is required.")}
          code={portalApiErrorCode(error, "METADATA_DESIGN_BLOCKED")}
        />
      </div>
    );
  }

  return (
    <MetadataDesignChat
      defaultDbProfileId={profiles.defaultProfileId}
      initialWorkMode={initialWorkMode}
      profiles={profiles.profiles}
    />
  );
}

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function initialWorkModeForIntent(value: string | undefined): MetadataDesignWorkMode {
  return value === "search" ? "SEARCH_METADATA" : "NEW_TABLE_DESIGN";
}
