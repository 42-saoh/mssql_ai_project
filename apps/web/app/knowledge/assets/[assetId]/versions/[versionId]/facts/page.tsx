import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { KnowledgeEdge, KnowledgeFact } from "@/lib/api/types";

export const dynamic = "force-dynamic";

function refsText(refs: string[]): string {
  return refs.length > 0 ? refs.join(", ") : "No evidence refs recorded";
}

export default async function KnowledgeFactsPage({
  params,
}: Readonly<{
  params: Promise<{ assetId: string; versionId: string }>;
}>) {
  const { assetId, versionId } = await params;
  try {
    const api = getPortalApi();
    const [asset, graph] = await Promise.all([
      api.getKnowledgeAsset(assetId),
      api.listKnowledgeFacts(assetId, versionId),
    ]);

    return (
      <div className="stack">
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Knowledge facts</p>
              <h1>{asset.assetKind}</h1>
            </div>
            <StatusPill value="DRAFT" label="Sanitized graph" />
          </div>
          <dl className="metric-grid">
            <div>
              <dt>Asset id</dt>
              <dd>{graph.assetId}</dd>
            </div>
            <div>
              <dt>Version id</dt>
              <dd>{graph.versionId}</dd>
            </div>
            <div>
              <dt>Facts</dt>
              <dd>{graph.facts.length}</dd>
            </div>
            <div>
              <dt>Edges</dt>
              <dd>{graph.edges.length}</dd>
            </div>
            {asset.targetKey ? (
              <div>
                <dt>targetKey</dt>
                <dd>
                  <code>{asset.targetKey}</code>
                </dd>
              </div>
            ) : null}
          </dl>
          <div className="page-actions">
            <Link className="secondary-action" href={`/knowledge/assets/${encodeURIComponent(assetId)}`}>
              Back to asset
            </Link>
            {asset.sourceJobId ? (
              <Link className="secondary-action" href={`/jobs/${encodeURIComponent(asset.sourceJobId)}`}>
                Source job
              </Link>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Facts</p>
              <h2>Sanitized fact rows</h2>
            </div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fact id</th>
                  <th>Type</th>
                  <th>Object</th>
                  <th>Status</th>
                  <th>Summary</th>
                  <th>Evidence refs</th>
                </tr>
              </thead>
              <tbody>
                {graph.facts.map((fact: KnowledgeFact) => (
                  <tr key={fact.factId}>
                    <td>
                      <code>{fact.factId}</code>
                    </td>
                    <td>{fact.factType}</td>
                    <td>{fact.objectRef}</td>
                    <td>
                      <StatusPill value={fact.status} label={fact.status} />
                    </td>
                    <td>{fact.summary}</td>
                    <td>{refsText(fact.evidenceRefs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Edges</p>
              <h2>Fact graph links</h2>
            </div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Edge id</th>
                  <th>Type</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Evidence refs</th>
                </tr>
              </thead>
              <tbody>
                {graph.edges.map((edge: KnowledgeEdge) => (
                  <tr key={edge.edgeId}>
                    <td>
                      <code>{edge.edgeId}</code>
                    </td>
                    <td>{edge.edgeType}</td>
                    <td>
                      <code>{edge.fromFactId}</code>
                    </td>
                    <td>
                      <code>{edge.toFactId}</code>
                    </td>
                    <td>{refsText(edge.evidenceRefs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Knowledge fact graph is unavailable"
          message={formatPortalApiError(error, "PLF knowledge fact graph is required.")}
          code={portalApiErrorCode(error, "P35_KNOWLEDGE_FACT_GRAPH_BLOCKED")}
        />
      </div>
    );
  }
}
