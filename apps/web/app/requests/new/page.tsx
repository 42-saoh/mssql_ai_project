import { RequestForm } from "@/components/request-form";
import { getPortalApi } from "@/lib/api/client";

export default async function NewRequestPage() {
  const api = getPortalApi();
  const profileResponse = await api.listMetadataProfiles();

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Request intake</p>
            <h1>Stored procedure analysis request</h1>
          </div>
          <span className="quiet-label">Draft only</span>
        </div>
        <p className="lede">
          Compose the OpenAPI-shaped request payload for one stored procedure target. This shell
          keeps submission in the mock adapter and never calls a live MSSQL database.
        </p>
      </section>

      <section className="panel">
        <RequestForm
          defaultProfileId={profileResponse.defaultProfileId}
          profiles={profileResponse.profiles}
        />
      </section>
    </div>
  );
}
