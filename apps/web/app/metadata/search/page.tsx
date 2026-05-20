import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { MetadataSearchObjectType } from "@/lib/api/types";
import { metadataCaveatMessages, splitMetadataBlockers } from "@/lib/display-caveats";

export const dynamic = "force-dynamic";

const objectTypeOptions: MetadataSearchObjectType[] = [
  "PROCEDURE",
  "TABLE",
  "COLUMN",
  "VIEW",
  "FUNCTION",
];

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function arrayParam(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value;
  }

  return value ? [value] : [];
}

function selectedObjectTypes(
  params: Record<string, string | string[] | undefined>,
): MetadataSearchObjectType[] {
  const requested = arrayParam(params.objectTypes).filter(
    (value): value is MetadataSearchObjectType =>
      objectTypeOptions.includes(value as MetadataSearchObjectType),
  );

  return requested.length > 0 ? requested : objectTypeOptions;
}

export default async function MetadataSearchPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const params = await searchParams;
  let api: PortalApi;
  try {
    api = getPortalApi();
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Portal API is not configured"
          message={formatPortalApiError(error, "PORTAL_API_BASE_URL is required.")}
        />
      </div>
    );
  }

  const dbProfileId = firstParam(params.dbProfileId) ?? "ppm";
  const query = firstParam(params.query)?.trim() || "P";
  const objectTypes = selectedObjectTypes(params);
  const limit = Number(firstParam(params.limit) ?? "10");
  const [profileResult, searchResult] = await Promise.allSettled([
    api.listMetadataProfiles(),
    api.searchMetadataObjects({
      dbProfileId,
      query,
      objectTypes,
      limit,
    }),
  ]);

  if (profileResult.status === "rejected" || searchResult.status === "rejected") {
    const reason =
      profileResult.status === "rejected"
        ? profileResult.reason
        : searchResult.status === "rejected"
          ? searchResult.reason
          : undefined;
    return (
      <div className="stack">
        <DependencyBlocker
          title="PPM metadata dependency is unavailable"
          message={formatPortalApiError(reason, "Live PPM metadata is required.")}
          code={portalApiErrorCode(reason, "P21_METADATA_SEARCH_BLOCKED")}
        />
      </div>
    );
  }

  const profileResponse = profileResult.value;
  const response = searchResult.value;
  const { caveatBlockers, hardBlockers } = splitMetadataBlockers(response.blockers);
  const responseCaveats = metadataCaveatMessages(response.caveats, caveatBlockers);

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Read-only metadata</p>
            <h1>Metadata search</h1>
          </div>
          <span className="quiet-label">MCP boundary</span>
        </div>
        <p className="lede">
          Search object and column identities, evidence refs, caveats, and blockers through the
          portal API adapter. Results never include row data, SQL definition text, procedure
          execution, or DDL/DML controls.
        </p>
      </section>

      <section className="panel">
        <form className="metadata-search-form" method="get">
          <div className="form-grid">
            <label>
              <span>Metadata profile</span>
              <select name="dbProfileId" defaultValue={dbProfileId}>
                {profileResponse.profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.id} - {profile.database}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Search query</span>
              <input name="query" defaultValue={query} placeholder="procedure, table, column" />
            </label>

            <label>
              <span>Limit</span>
              <input min="1" max="100" name="limit" type="number" defaultValue={response.limit} />
            </label>
          </div>

          <fieldset>
            <legend>Object types</legend>
            <div className="toggle-row">
              {objectTypeOptions.map((objectType) => (
                <label key={objectType}>
                  <input
                    type="checkbox"
                    name="objectTypes"
                    value={objectType}
                    defaultChecked={objectTypes.includes(objectType)}
                  />
                  {objectType}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="form-actions">
            <button type="submit">Search metadata</button>
            <Link className="secondary-action" href="/requests/new">
              Use in request
            </Link>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Search results</p>
            <h2>
              {response.sourceDatabase}.{response.query}
            </h2>
          </div>
          <StatusPill
            value={response.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
            label={response.reviewRequired ? "근거 보강 필요" : "Evidence only"}
          />
        </div>

        <dl className="metric-grid">
          <div>
            <dt>Profile</dt>
            <dd>{response.sourceProfile}</dd>
          </div>
          <div>
            <dt>Database</dt>
            <dd>{response.sourceDatabase}</dd>
          </div>
          <div>
            <dt>Results</dt>
            <dd>{response.results.length}</dd>
          </div>
        </dl>

        {hardBlockers.length > 0 ? (
          <div className="blocker-list">
            {hardBlockers.map((blocker) => (
              <article className="blocker-row" key={blocker.code}>
                <strong>{blocker.code}</strong>
                <span>{blocker.message}</span>
              </article>
            ))}
          </div>
        ) : null}

        {responseCaveats.length > 0 ? (
          <div className="callout">
            <strong>Evidence caveats</strong>
            <ul>
              {responseCaveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="metadata-result-list">
          {response.results.map((result) => {
            const identity = result.objectIdentity;
            const fullName = `${identity.schema}.${identity.name}`;
            const resultCaveats = metadataCaveatMessages(result.caveats, result.blockers);

            return (
              <article className="metadata-result-row" key={`${identity.type}-${fullName}`}>
                <div>
                  <p className="eyebrow">{identity.type}</p>
                  <h3>{fullName}</h3>
                  <p>
                    {result.sourceProfile} - {result.sourceDatabase}
                    {result.snapshotId ? ` - ${result.snapshotId}` : ""}
                  </p>
                  {result.targetKey ? <code>{result.targetKey}</code> : null}
                </div>
                <div className="metadata-result-detail">
                  <StatusPill
                    value={result.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
                    label={result.reviewRequired ? "근거 보강 필요" : "Evidence only"}
                  />
                  {result.evidenceRefs.map((evidence) => (
                    <code key={`${fullName}-${evidence.locator}`}>{evidence.locator}</code>
                  ))}
                  {resultCaveats.length > 0 ? (
                    <small>{resultCaveats.join(" · ")}</small>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>

    </div>
  );
}
