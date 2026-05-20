import Link from "next/link";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { MetadataToolInvokeResponse, MetadataToolName, TargetObjectType } from "@/lib/api/types";

export const dynamic = "force-dynamic";

type DependencyMode = "closure" | "resolver";
type SourceObjectType = Extract<TargetObjectType, "PROCEDURE" | "VIEW" | "FUNCTION">;

const dependencyObjectTypes: SourceObjectType[] = ["PROCEDURE", "VIEW", "FUNCTION"];

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function cleanParam(
  params: Record<string, string | string[] | undefined>,
  name: string,
  fallback: string,
): string {
  return firstParam(params[name])?.trim() || fallback;
}

function numberParam(
  params: Record<string, string | string[] | undefined>,
  name: string,
  fallback: number,
): number {
  const value = Number(firstParam(params[name]) ?? fallback);
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(Math.max(Math.trunc(value), 0), 3);
}

function booleanParam(
  params: Record<string, string | string[] | undefined>,
  name: string,
  fallback: boolean,
): boolean {
  const value = firstParam(params[name]);
  if (value === undefined) {
    return fallback;
  }
  return ["1", "true", "on", "yes"].includes(value.toLowerCase());
}

function modeParam(params: Record<string, string | string[] | undefined>): DependencyMode {
  return firstParam(params.mode) === "resolver" ? "resolver" : "closure";
}

function sourceObjectTypeParam(
  params: Record<string, string | string[] | undefined>,
  name: string,
): SourceObjectType {
  const value = firstParam(params[name]);
  return dependencyObjectTypes.includes(value as SourceObjectType)
    ? (value as SourceObjectType)
    : "PROCEDURE";
}

function optionalParam(
  params: Record<string, string | string[] | undefined>,
  name: string,
): string | undefined {
  const value = firstParam(params[name])?.trim();
  return value || undefined;
}

function dictItems(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> =>
    typeof item === "object" && item !== null && !Array.isArray(item),
  );
}

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function objectLabel(value: Record<string, unknown>): string {
  const schema = text(value.schema);
  const name = text(value.name);
  if (schema && name) {
    return `${schema}.${name}`;
  }
  return name || text(value.id, "unresolved");
}

function evidenceLocator(value: Record<string, unknown>): string {
  return text(value.locator) || text(value.path) || text(value.source) || "mssql-mcp";
}

function evidenceObject(value: Record<string, unknown>): string {
  return text(value.objectRef) || text(value.objectName) || text(value.id) || "metadata";
}

function statusValue(value: unknown): "PASSED" | "REVIEW_REQUIRED" {
  return text(value) === "CONFIRMED" ? "PASSED" : "REVIEW_REQUIRED";
}

function statusLabel(value: unknown, fallback = "근거 보강 필요"): string {
  return text(value) === "CONFIRMED" ? "Confirmed" : fallback;
}

function invocationFor(
  mode: DependencyMode,
  params: Record<string, string | string[] | undefined>,
): { toolName: MetadataToolName; arguments: Record<string, unknown> } {
  const dbProfileId = cleanParam(params, "dbProfileId", "ppm");
  if (mode === "resolver") {
    return {
      toolName: "resolve_dependency_reference",
      arguments: {
        dbProfileId,
        sourceObject: {
          schema: cleanParam(params, "sourceSchema", "dbo"),
          name: cleanParam(params, "sourceName", "GetInspItemsCd"),
          objectType: sourceObjectTypeParam(params, "sourceObjectType"),
        },
        referencedSchema: optionalParam(params, "referencedSchema") ?? "dbo",
        referencedName: cleanParam(params, "referencedName", "PEX_INSP_ITEMS"),
        referencedDatabase: optionalParam(params, "referencedDatabase"),
        referencedServer: optionalParam(params, "referencedServer"),
      },
    };
  }
  return {
    toolName: "get_dependency_closure",
    arguments: {
      dbProfileId,
      schema: cleanParam(params, "schema", "dbo"),
      objectName: cleanParam(params, "objectName", "GetInspItemsCd"),
      objectType: sourceObjectTypeParam(params, "objectType"),
      maxDepth: numberParam(params, "maxDepth", 2),
      includeReviewRequired: booleanParam(params, "includeReviewRequired", false),
    },
  };
}

export default async function MetadataDependenciesPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const params = await searchParams;
  const mode = modeParam(params);
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

  const [profileResult, toolResult] = await Promise.allSettled([
    api.listMetadataProfiles(),
    api.listMetadataTools(),
  ]);
  if (profileResult.status === "rejected" || toolResult.status === "rejected") {
    const reason =
      profileResult.status === "rejected"
        ? profileResult.reason
        : toolResult.status === "rejected"
          ? toolResult.reason
          : undefined;
    return (
      <div className="stack">
        <DependencyBlocker
          title="Dependency diagnostics are unavailable"
          message={formatPortalApiError(reason, "Metadata tool summary is required.")}
          code={portalApiErrorCode(reason, "METADATA_TOOL_SUMMARY_BLOCKED")}
        />
      </div>
    );
  }

  const invocation = invocationFor(mode, params);
  const invokableTools = new Set(
    toolResult.value.tools.filter((tool) => tool.invokable).map((tool) => tool.name),
  );
  const invocationResult = invokableTools.has(invocation.toolName)
    ? await Promise.allSettled([
        api.invokeMetadataTool(invocation.toolName, { arguments: invocation.arguments }),
      ])
    : [
        {
          status: "rejected" as const,
          reason: new Error(`${invocation.toolName} is not public-invokable.`),
        },
      ];
  const result = invocationResult[0];

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Read-only dependency evidence</p>
            <h1>Dependency diagnostics</h1>
          </div>
          <span className="quiet-label">MCP registry</span>
        </div>
        <div className="tab-row" role="tablist" aria-label="Dependency tool mode">
          <Link
            className={mode === "closure" ? "tab-link tab-link--active" : "tab-link"}
            href="/metadata/dependencies?mode=closure"
          >
            Closure
          </Link>
          <Link
            className={mode === "resolver" ? "tab-link tab-link--active" : "tab-link"}
            href="/metadata/dependencies?mode=resolver"
          >
            Resolve reference
          </Link>
        </div>
      </section>

      <section className="panel">
        <ToolSummary tools={toolResult.value.tools} />
      </section>

      <section className="panel">
        {mode === "resolver" ? (
          <ResolverForm params={params} profiles={profileResult.value.profiles} />
        ) : (
          <ClosureForm params={params} profiles={profileResult.value.profiles} />
        )}
      </section>

      <section className="panel">
        {result.status === "fulfilled" ? (
          <InvocationResult response={result.value} />
        ) : (
          <DependencyBlocker
            title="Dependency evidence tool failed"
            message={formatPortalApiError(result.reason, "Dependency evidence is unavailable.")}
            code={portalApiErrorCode(result.reason, "DEPENDENCY_EVIDENCE_BLOCKED")}
          />
        )}
      </section>
    </div>
  );
}

function ToolSummary({
  tools,
}: Readonly<{
  tools: { name: string; invokable: boolean; readOnly: true }[];
}>) {
  return (
    <div className="tool-summary-grid">
      {tools
        .filter((tool) =>
          ["get_dependency_closure", "resolve_dependency_reference"].includes(tool.name),
        )
        .map((tool) => (
          <div key={tool.name}>
            <code>{tool.name}</code>
            <StatusPill
              value={tool.invokable ? "PASSED" : "REVIEW_REQUIRED"}
              label={tool.invokable ? "Invokable" : "Summary only"}
            />
          </div>
        ))}
    </div>
  );
}

function ProfileSelect({
  profiles,
  dbProfileId,
}: Readonly<{
  profiles: { id: string; database: string }[];
  dbProfileId: string;
}>) {
  return (
    <select name="dbProfileId" defaultValue={dbProfileId}>
      {profiles.map((profile) => (
        <option key={profile.id} value={profile.id}>
          {profile.id} - {profile.database}
        </option>
      ))}
    </select>
  );
}

function ObjectTypeSelect({
  name,
  value,
}: Readonly<{
  name: string;
  value: SourceObjectType;
}>) {
  return (
    <select name={name} defaultValue={value}>
      {dependencyObjectTypes.map((objectType) => (
        <option key={objectType} value={objectType}>
          {objectType}
        </option>
      ))}
    </select>
  );
}

function ClosureForm({
  params,
  profiles,
}: Readonly<{
  params: Record<string, string | string[] | undefined>;
  profiles: { id: string; database: string }[];
}>) {
  const dbProfileId = cleanParam(params, "dbProfileId", "ppm");
  const includeReviewRequired = booleanParam(params, "includeReviewRequired", false);
  return (
    <form className="metadata-search-form" method="get">
      <input type="hidden" name="mode" value="closure" />
      <div className="form-grid">
        <label>
          <span>Metadata profile</span>
          <ProfileSelect profiles={profiles} dbProfileId={dbProfileId} />
        </label>
        <label>
          <span>Object type</span>
          <ObjectTypeSelect name="objectType" value={sourceObjectTypeParam(params, "objectType")} />
        </label>
        <label>
          <span>Schema</span>
          <input name="schema" defaultValue={cleanParam(params, "schema", "dbo")} />
        </label>
        <label>
          <span>Object name</span>
          <input
            name="objectName"
            defaultValue={cleanParam(params, "objectName", "GetInspItemsCd")}
          />
        </label>
        <label>
          <span>Max depth</span>
          <input
            min="0"
            max="3"
            name="maxDepth"
            type="number"
            defaultValue={numberParam(params, "maxDepth", 2)}
          />
        </label>
      </div>
      <div className="toggle-row">
        <label>
          <input
            type="checkbox"
            name="includeReviewRequired"
            value="true"
            defaultChecked={includeReviewRequired}
          />
          Include evidence-caveated graph items
        </label>
      </div>
      <div className="form-actions">
        <button type="submit">Invoke closure</button>
        <Link className="secondary-action" href="/metadata/search">
          Search metadata
        </Link>
      </div>
    </form>
  );
}

function ResolverForm({
  params,
  profiles,
}: Readonly<{
  params: Record<string, string | string[] | undefined>;
  profiles: { id: string; database: string }[];
}>) {
  const dbProfileId = cleanParam(params, "dbProfileId", "ppm");
  return (
    <form className="metadata-search-form" method="get">
      <input type="hidden" name="mode" value="resolver" />
      <div className="form-grid">
        <label>
          <span>Metadata profile</span>
          <ProfileSelect profiles={profiles} dbProfileId={dbProfileId} />
        </label>
        <label>
          <span>Source type</span>
          <ObjectTypeSelect
            name="sourceObjectType"
            value={sourceObjectTypeParam(params, "sourceObjectType")}
          />
        </label>
        <label>
          <span>Source schema</span>
          <input name="sourceSchema" defaultValue={cleanParam(params, "sourceSchema", "dbo")} />
        </label>
        <label>
          <span>Source name</span>
          <input
            name="sourceName"
            defaultValue={cleanParam(params, "sourceName", "GetInspItemsCd")}
          />
        </label>
        <label>
          <span>Referenced schema</span>
          <input
            name="referencedSchema"
            defaultValue={cleanParam(params, "referencedSchema", "dbo")}
          />
        </label>
        <label>
          <span>Referenced name</span>
          <input
            name="referencedName"
            defaultValue={cleanParam(params, "referencedName", "PEX_INSP_ITEMS")}
          />
        </label>
        <label>
          <span>Referenced database</span>
          <input name="referencedDatabase" defaultValue={optionalParam(params, "referencedDatabase")} />
        </label>
        <label>
          <span>Referenced server</span>
          <input name="referencedServer" defaultValue={optionalParam(params, "referencedServer")} />
        </label>
      </div>
      <div className="form-actions">
        <button type="submit">Invoke resolver</button>
        <Link className="secondary-action" href="/metadata/search">
          Search metadata
        </Link>
      </div>
    </form>
  );
}

function InvocationResult({
  response,
}: Readonly<{
  response: MetadataToolInvokeResponse;
}>) {
  const data = response.data;
  return (
    <div className="stack">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{response.toolName}</p>
          <h2>{response.dbProfileId}</h2>
        </div>
        <StatusPill
          value={data.reviewRequired ? "REVIEW_REQUIRED" : "PASSED"}
          label={data.reviewRequired ? "근거 보강 필요" : "Evidence only"}
        />
      </div>
      <dl className="metric-grid">
        <div>
          <dt>Snapshot</dt>
          <dd>{response.snapshotId}</dd>
        </div>
        <div>
          <dt>Collected</dt>
          <dd>{response.collectedAt}</dd>
        </div>
        <div>
          <dt>Evidence refs</dt>
          <dd>{response.evidenceRefs.length}</dd>
        </div>
      </dl>
      {response.toolName === "get_dependency_closure" ? (
        <ClosureResult data={data} />
      ) : (
        <ResolverResult data={data} />
      )}
      <EvidenceRefs refs={response.evidenceRefs} />
    </div>
  );
}

function ClosureResult({
  data,
}: Readonly<{
  data: Record<string, unknown>;
}>) {
  const summary = typeof data.summary === "object" && data.summary ? data.summary : {};
  const nodes = dictItems(data.nodes);
  const edges = dictItems(data.edges);
  const unresolved = dictItems(data.unresolved);
  return (
    <div className="stack">
      <dl className="metric-grid">
        <div>
          <dt>Nodes</dt>
          <dd>{text((summary as Record<string, unknown>).nodeCount, String(nodes.length))}</dd>
        </div>
        <div>
          <dt>Edges</dt>
          <dd>{text((summary as Record<string, unknown>).edgeCount, String(edges.length))}</dd>
        </div>
        <div>
          <dt>Unresolved</dt>
          <dd>
            {text(
              (summary as Record<string, unknown>).reviewRequiredCount,
              String(unresolved.length),
            )}
          </dd>
        </div>
      </dl>
      <ResultList title="Nodes">
        {nodes.map((node) => (
          <article className="metadata-result-row" key={text(node.id, objectLabel(node))}>
            <div>
              <p className="eyebrow">{text(node.objectType, "OBJECT")}</p>
              <h3>{objectLabel(node)}</h3>
              <p>{text(node.database, "metadata")}</p>
            </div>
            <StatusPill
              value={statusValue(node.reviewStatus)}
              label={statusLabel(node.reviewStatus)}
            />
          </article>
        ))}
      </ResultList>
      <ResultList title="Edges">
        {edges.map((edge, index) => (
          <article className="metadata-result-row" key={`${text(edge.from)}-${text(edge.to)}-${index}`}>
            <div>
              <p className="eyebrow">{text(edge.dependencyType, "REFERENCE")}</p>
              <h3>{text(edge.to, "dependency target")}</h3>
              <p>{text(edge.resolutionStrategy, "UNRESOLVED")}</p>
            </div>
            <StatusPill
              value={statusValue(edge.resolutionStatus)}
              label={statusLabel(edge.resolutionStatus)}
            />
          </article>
        ))}
      </ResultList>
      <ResultList title="Unresolved">
        {unresolved.map((item, index) => (
          <article className="metadata-result-row" key={`${objectLabel(item)}-${index}`}>
            <div>
              <p className="eyebrow">{text(item.dependencyType, "REFERENCE")}</p>
              <h3>{objectLabel(item)}</h3>
              <p>{text(item.resolutionStrategy, "UNRESOLVED")}</p>
            </div>
            <StatusPill
              value={statusValue(item.resolutionStatus)}
              label={statusLabel(item.resolutionStatus)}
            />
          </article>
        ))}
      </ResultList>
    </div>
  );
}

function ResolverResult({
  data,
}: Readonly<{
  data: Record<string, unknown>;
}>) {
  const selected =
    typeof data.selectedResolution === "object" && data.selectedResolution
      ? (data.selectedResolution as Record<string, unknown>)
      : null;
  const candidates = dictItems(data.candidates);
  return (
    <div className="stack">
      <div className="callout">
        <strong>{selected ? "Selected resolution" : "Selected resolution unavailable"}</strong>
        <p>
          {selected
            ? `${objectLabel(selected)} - ${text(selected.resolutionStrategy, "CONFIRMED")}`
            : statusLabel(data.resolutionStrategy)}
        </p>
      </div>
      <ResultList title="Candidates">
        {candidates.map((candidate, index) => (
          <article className="metadata-result-row" key={`${objectLabel(candidate)}-${index}`}>
            <div>
              <p className="eyebrow">{text(candidate.objectType, "OBJECT")}</p>
              <h3>{objectLabel(candidate)}</h3>
              <p>{text(candidate.resolutionEvidenceKind, "metadata evidence")}</p>
            </div>
            <StatusPill
              value={statusValue(candidate.resolutionStatus)}
              label={text(candidate.resolutionConfidence, "UNKNOWN")}
            />
          </article>
        ))}
      </ResultList>
    </div>
  );
}

function ResultList({
  title,
  children,
}: Readonly<{
  title: string;
  children: React.ReactNode;
}>) {
  return (
    <div className="stack">
      <h2 className="compact-heading">{title}</h2>
      <div className="metadata-result-list">{children}</div>
    </div>
  );
}

function EvidenceRefs({
  refs,
}: Readonly<{
  refs: Record<string, unknown>[];
}>) {
  return (
    <div className="stack">
      <h2 className="compact-heading">Evidence refs</h2>
      <div className="evidence-list">
        {refs.map((ref, index) => (
          <div className="evidence-row" key={`${evidenceObject(ref)}-${evidenceLocator(ref)}-${index}`}>
            <strong>{evidenceObject(ref)}</strong>
            <code>{evidenceLocator(ref)}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
