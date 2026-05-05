import { RequestForm } from "@/components/request-form";
import { getPortalApi } from "@/lib/api/client";
import { getPilotManifestSummary } from "@/lib/pilot-manifest";

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function NewRequestPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const api = getPortalApi();
  const [profileResponse, params] = await Promise.all([api.listMetadataProfiles(), searchParams]);
  const pilotManifest = getPilotManifestSummary();
  const requestedSampleId = firstParam(params.sample);
  const selectedSample =
    pilotManifest.procedureSamples.find((sample) => sample.id === requestedSampleId) ??
    pilotManifest.procedureSamples[0];

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
          pilotManifest={pilotManifest}
          selectedSample={selectedSample}
        />
      </section>
    </div>
  );
}
