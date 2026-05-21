import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { KnowledgeAssetVersion } from "@/lib/api/types";

export const dynamic = "force-dynamic";

function formatDateTime(value?: string): string {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function factsHref(assetId: string, versionId: string): string {
  return `/knowledge/assets/${encodeURIComponent(assetId)}/versions/${encodeURIComponent(
    versionId,
  )}/facts`;
}

export default async function KnowledgeAssetPage({
  params,
}: Readonly<{
  params: Promise<{ assetId: string }>;
}>) {
  const { assetId } = await params;
  try {
    const api = getPortalApi();
    const [asset, versionResponse] = await Promise.all([
      api.getKnowledgeAsset(assetId),
      api.listKnowledgeAssetVersions(assetId),
    ]);
    const versions = versionResponse.versions;
    const currentVersion =
      versions.find((version) => version.versionId === asset.currentVersionId) ?? versions[0];

    return (
      <div className="stack">
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Knowledge asset</p>
              <h1>{asset.assetKind}</h1>
            </div>
            <StatusPill value="DRAFT" label="Draft knowledge" />
          </div>

          <dl className="metric-grid">
            <div>
              <dt>Asset id</dt>
              <dd>{asset.assetId}</dd>
            </div>
            <div>
              <dt>Profile</dt>
              <dd>{asset.dbProfileId}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>
                {asset.targetSchema}.{asset.targetName}
              </dd>
            </div>
            <div>
              <dt>Current version</dt>
              <dd>v{asset.currentVersionNo}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{formatDateTime(asset.updatedAt ?? asset.createdAt)}</dd>
            </div>
            <div>
              <dt>Source job</dt>
              <dd>
                {asset.sourceJobId ? (
                  <Link href={`/jobs/${encodeURIComponent(asset.sourceJobId)}`}>
                    {asset.sourceJobId}
                  </Link>
                ) : (
                  "Not recorded"
                )}
              </dd>
            </div>
            {asset.targetKey ? (
              <div>
                <dt>targetKey</dt>
                <dd>
                  <code>{asset.targetKey}</code>
                </dd>
              </div>
            ) : null}
            <div>
              <dt>Logical key</dt>
              <dd>
                <code>{asset.logicalKey}</code>
              </dd>
            </div>
            <div>
              <dt>Content hash</dt>
              <dd>
                <code>{asset.contentHash ?? "pending"}</code>
              </dd>
            </div>
          </dl>

          <div className="page-actions">
            {currentVersion ? (
              <Link className="primary-action" href={factsHref(asset.assetId, currentVersion.versionId)}>
                Open current facts
              </Link>
            ) : null}
            {asset.targetKey ? (
              <Link
                className="secondary-action"
                href={`/jobs?targetKey=${encodeURIComponent(asset.targetKey)}`}
              >
                Same target history
              </Link>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Version history</p>
              <h2>Sanitized fact graph versions</h2>
            </div>
            <span className="quiet-label">{versions.length} versions</span>
          </div>
          <div className="artifact-list">
            {versions.map((version: KnowledgeAssetVersion) => (
              <article className="artifact-row" key={version.versionId}>
                <div>
                  <h3>v{version.versionNo}</h3>
                  <p>
                    {version.factCount} facts - {version.edgeCount} edges -{" "}
                    {formatDateTime(version.createdAt)}
                  </p>
                  <small>
                    content <code>{version.contentHash}</code>
                  </small>
                </div>
                <div className="row-actions">
                  <Link href={factsHref(asset.assetId, version.versionId)}>Facts</Link>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    );
  } catch (error) {
    return (
      <div className="stack">
        <DependencyBlocker
          title="Knowledge asset is unavailable"
          message={formatPortalApiError(error, "PLF knowledge repository is required.")}
          code={portalApiErrorCode(error, "P35_KNOWLEDGE_ASSET_BLOCKED")}
        />
      </div>
    );
  }
}
