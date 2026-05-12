import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { MetadataAnalysisResponse, MetadataSearchObjectType } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const objectTypeOptions: MetadataSearchObjectType[] = [
  "PROCEDURE",
  "TABLE",
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
  const requested = arrayParam(params.objectTypes).filter((value): value is MetadataSearchObjectType =>
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
  const shouldAnalyze = firstParam(params.analyze) === "1";
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
  let analysis: MetadataAnalysisResponse | null = null;
  let analysisError: unknown = null;
  if (shouldAnalyze) {
    try {
      analysis = await api.analyzeMetadata({
        dbProfileId,
        query,
        objectTypes,
        options: {
          useLlmAnalysis: true,
          useAiToolOrchestration: true,
          llmProfileId: "openai_sp_semantic_analysis",
          maxTargets: Math.min(Math.max(limit, 1), 5),
        },
      });
    } catch (error) {
      analysisError = error;
    }
  }

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
          Search object identities, evidence refs, caveats, and blockers through the portal API
          adapter. Results never include row data, SQL definition text, procedure execution, or
          DDL/DML controls.
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
              <input name="query" defaultValue={query} placeholder="procedure, table, view" />
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
            <button type="submit" name="analyze" value="1">
              Analyze metadata
            </button>
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
            label={response.reviewRequired ? "Review required" : "Evidence only"}
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

        {response.blockers.length > 0 ? (
          <div className="blocker-list">
            {response.blockers.map((blocker) => (
              <article className="blocker-row" key={blocker.code}>
                <strong>{blocker.code}</strong>
                <span>{blocker.message}</span>
              </article>
            ))}
          </div>
        ) : null}

        {response.caveats.length > 0 ? (
          <div className="callout">
            <strong>Caveats</strong>
            <ul>
              {response.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="metadata-result-list">
          {response.results.map((result) => {
            const identity = result.objectIdentity;
            const fullName = `${identity.schema}.${identity.name}`;

            return (
              <article className="metadata-result-row" key={`${identity.type}-${fullName}`}>
                <div>
                  <p className="eyebrow">{identity.type}</p>
                  <h3>{fullName}</h3>
                  <p>
                    {result.sourceProfile} · {result.sourceDatabase}
                    {result.snapshotId ? ` · ${result.snapshotId}` : ""}
                  </p>
                </div>
                <div className="metadata-result-detail">
                  <StatusPill
                    value={result.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
                    label={result.reviewRequired ? "Review required" : "Evidence only"}
                  />
                  {result.evidenceRefs.map((evidence) => (
                    <code key={`${fullName}-${evidence.locator}`}>{evidence.locator}</code>
                  ))}
                  {result.caveats.length > 0 ? (
                    <small>{result.caveats.join(", ")}</small>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {analysisError ? (
        <section className="panel">
          <DependencyBlocker
            title="Metadata analysis is unavailable"
            message={formatPortalApiError(analysisError, "Metadata analysis could not run.")}
            code={portalApiErrorCode(analysisError, "AI_METADATA_ANALYSIS_BLOCKED")}
          />
        </section>
      ) : null}

      {analysis ? <MetadataAnalysisPanel analysis={analysis} /> : null}
    </div>
  );
}

function MetadataAnalysisPanel({ analysis }: Readonly<{ analysis: MetadataAnalysisResponse }>) {
  const toolEvidence = analysis.aiToolEvidence;
  const plannerMetrics = toolEvidence.plannerMetrics;

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">AI-MCP metadata analysis</p>
          <h2>{analysis.sourceDatabase}.{analysis.query ?? analysis.target?.name ?? "target"}</h2>
        </div>
        <StatusPill
          value={analysis.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
          label={analysis.reviewRequired ? "Review required" : "Evidence linked"}
        />
      </div>

      <dl className="metric-grid">
        <div>
          <dt>Facts</dt>
          <dd>{analysis.deterministicFacts.length}</dd>
        </div>
        <div>
          <dt>Tools</dt>
          <dd>{toolEvidence.toolCallCount ?? 0}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{toolEvidence.status ?? "SKIPPED"}</dd>
        </div>
        <div>
          <dt>Evidence use</dt>
          <dd>{formatRatio(plannerMetrics?.evidenceUtilization)}</dd>
        </div>
        <div>
          <dt>Claim support</dt>
          <dd>{formatRatio(plannerMetrics?.claimSupportRate)}</dd>
        </div>
        <div>
          <dt>Objects</dt>
          <dd>{analysis.objectProfiles.length}</dd>
        </div>
        <div>
          <dt>Edges</dt>
          <dd>{analysis.dependencyGraph.edges.length}</dd>
        </div>
      </dl>

      {plannerMetrics ? (
        <div className="callout">
          <strong>Planner effectiveness</strong>
          <p>
            {plannerMetrics.status ?? "PENDING"} · {plannerMetrics.plannedRequestCount ?? 0} planned ·{" "}
            {plannerMetrics.executedToolCallCount ?? 0} executed ·{" "}
            {plannerMetrics.blockedRequestCount ?? 0} blocked ·{" "}
            {plannerMetrics.failedToolCallCount ?? 0} failed
          </p>
        </div>
      ) : null}

      <p>{analysis.summary}</p>

      {analysis.objectProfiles.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.objectProfiles.map((profile) => (
            <article className="metadata-result-row" key={profile.objectRef}>
              <div>
                <p className="eyebrow">{profile.objectType}</p>
                <h3>{profile.objectRef}</h3>
                <p>
                  {profile.columnCount} columns · {profile.primaryKeyCount} PK ·{" "}
                  {profile.foreignKeyCount} FK · {profile.indexCount} indexes
                </p>
              </div>
              <div className="metadata-result-detail">
                <StatusPill
                  value={profile.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
                  label={`${Math.round(profile.descriptionCoverage * 100)}% docs`}
                />
                {profile.sourceFactIds.slice(0, 3).map((ref) => (
                  <code key={`${profile.objectRef}-${ref}`}>{ref}</code>
                ))}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.dependencyGraph.nodes.length > 0 ? (
        <div className="callout">
          <strong>Dependency graph</strong>
          <p>
            {analysis.dependencyGraph.nodes.length} nodes ·{" "}
            {analysis.dependencyGraph.edges.length} edges ·{" "}
            {analysis.dependencyGraph.unresolved.length} unresolved
          </p>
        </div>
      ) : null}

      {analysis.dtoReadiness.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.dtoReadiness.map((item) => (
            <article className="metadata-result-row" key={`dto-${item.objectRef}`}>
              <div>
                <p className="eyebrow">DTO {item.status}</p>
                <h3>{item.objectRef}</h3>
                <p>{item.fieldCount} candidate fields</p>
              </div>
              <div className="metadata-result-detail">
                {item.reviewReasons.slice(0, 3).map((reason) => (
                  <small key={`${item.objectRef}-${reason}`}>{reason}</small>
                ))}
                {item.evidenceRefs.slice(0, 2).map((ref) => (
                  <code key={`dto-${item.objectRef}-${ref}`}>{ref}</code>
                ))}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.insightGroups.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.insightGroups.map((group) => (
            <article className="metadata-result-row" key={group.category}>
              <div>
                <p className="eyebrow">{group.category}</p>
                <h3>{group.insights.length} insights</h3>
                {group.insights.slice(0, 3).map((insight) => (
                  <p key={`${group.category}-${insight.code}`}>
                    <strong>{insight.code}</strong> · {insight.summary}
                  </p>
                ))}
              </div>
              <div className="metadata-result-detail">
                {group.insights
                  .flatMap((insight) => insight.evidenceRefs)
                  .slice(0, 4)
                  .map((ref) => (
                    <code key={`${group.category}-${ref}`}>{ref}</code>
                  ))}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.objectInsights.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.objectInsights.map((insight) => (
            <article className="metadata-result-row" key={`${insight.code}-${insight.objectRef}`}>
              <div>
                <p className="eyebrow">{insight.status}</p>
                <h3>{insight.code}</h3>
                <p>{insight.summary}</p>
              </div>
              <div className="metadata-result-detail">
                <code>{insight.objectRef}</code>
                {insight.evidenceRefs.map((ref) => (
                  <code key={`${insight.code}-${ref}`}>{ref}</code>
                ))}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.reviewMarkers.length > 0 ? (
        <div className="blocker-list">
          {analysis.reviewMarkers.map((marker) => (
            <article className="blocker-row" key={marker.code}>
              <strong>{marker.code}</strong>
              <span>{marker.message}</span>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.caveats.length > 0 ? (
        <div className="callout">
          <strong>Caveats</strong>
          <ul>
            {analysis.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function formatRatio(value: number | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}
