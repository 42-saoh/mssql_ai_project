import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { MetadataAnalysisResponse } from "@/lib/api/types";

export function MetadataAnalysisPanel({
  analysis,
}: Readonly<{ analysis: MetadataAnalysisResponse }>) {
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
          label={analysis.reviewRequired ? "근거 보강 필요" : "Evidence linked"}
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
            {plannerMetrics.status ?? "PENDING"} - {plannerMetrics.plannedRequestCount ?? 0}{" "}
            planned - {plannerMetrics.executedToolCallCount ?? 0} executed -{" "}
            {plannerMetrics.blockedRequestCount ?? 0} blocked -{" "}
            {plannerMetrics.failedToolCallCount ?? 0} failed
          </p>
        </div>
      ) : null}

      <p>{analysis.summary}</p>

      {analysis.knowledgeAssets.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.knowledgeAssets.map((asset) => (
            <article className="metadata-result-row" key={asset.assetId}>
              <div>
                <p className="eyebrow">Knowledge {asset.assetKind}</p>
                <h3>
                  {asset.targetSchema}.{asset.targetName}
                </h3>
                <p>
                  version {asset.currentVersionNo} - content {asset.contentHash ?? "pending"}
                </p>
              </div>
              <div className="metadata-result-detail">
                <Link href={`/api/v1/knowledge/assets/${asset.assetId}`}>Asset</Link>
                {asset.currentVersionId ? (
                  <Link
                    href={`/api/v1/knowledge/assets/${asset.assetId}/versions/${asset.currentVersionId}/facts`}
                  >
                    Facts
                  </Link>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {analysis.objectProfiles.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.objectProfiles.map((profile) => (
            <article className="metadata-result-row" key={profile.objectRef}>
              <div>
                <p className="eyebrow">{profile.objectType}</p>
                <h3>{profile.objectRef}</h3>
                <p>
                  {profile.columnCount} columns - {profile.primaryKeyCount} PK -{" "}
                  {profile.foreignKeyCount} FK - {profile.indexCount} indexes
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
            {analysis.dependencyGraph.nodes.length} nodes -{" "}
            {analysis.dependencyGraph.edges.length} edges -{" "}
            {analysis.dependencyGraph.unresolved.length} unresolved
          </p>
        </div>
      ) : null}

      {analysis.dtoReadiness.length > 0 ? (
        <div className="metadata-result-list">
          {analysis.dtoReadiness.map((item) => (
            <article className="metadata-result-row" key={`dto-${item.objectRef}`}>
              <div>
                <p className="eyebrow">DTO {evidenceStatusLabel(item.status)}</p>
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
                {group.insights.slice(0, 3).map((insight, index) => (
                  <p key={`${group.category}-${insight.code}-${insight.objectRef}-${index}`}>
                    <strong>{insight.code}</strong> - {insight.summary}
                  </p>
                ))}
              </div>
              <div className="metadata-result-detail">
                {group.insights
                  .flatMap((insight) => insight.evidenceRefs)
                  .slice(0, 4)
                  .map((ref, index) => (
                    <code key={`${group.category}-${ref}-${index}`}>{ref}</code>
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
                <p className="eyebrow">{evidenceStatusLabel(insight.status)}</p>
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
        <div className="blocker-list" aria-label="Evidence caveats">
          <p className="eyebrow">Evidence caveats</p>
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

function evidenceStatusLabel(status: string): string {
  if (status === "REVIEW_REQUIRED") {
    return "근거 보강 필요";
  }
  return status.replaceAll("_", " ");
}
