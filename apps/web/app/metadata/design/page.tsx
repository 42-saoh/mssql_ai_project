import { DependencyBlocker } from "@/components/dependency-blocker";
import { MetadataDesignChat } from "@/components/metadata-design-chat";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";

export const dynamic = "force-dynamic";

export default async function MetadataDesignPage() {
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
      profiles={profiles.profiles}
    />
  );
}
