import Link from "next/link";
import { redirect } from "next/navigation";
import { DependencyBlocker } from "@/components/dependency-blocker";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import { formatPortalApiError, portalApiErrorCode } from "@/lib/api/errors";
import type { PortalApi } from "@/lib/api/portal-api";
import type { ApprovalDecision, Artifact, ValidationReport } from "@/lib/api/types";
import { artifactStatusLabels, validationStatusLabels } from "@/lib/presentation";

export const dynamic = "force-dynamic";

const decisions: ApprovalDecision[] = ["REQUEST_CHANGES", "APPROVE", "REJECT"];

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function decisionParam(value: string | undefined): ApprovalDecision {
  return decisions.includes(value as ApprovalDecision)
    ? (value as ApprovalDecision)
    : "REQUEST_CHANGES";
}

async function recordDecision(formData: FormData) {
  "use server";

  const artifactId = String(formData.get("artifactId") ?? "");
  const validationReportId = String(formData.get("validationReportId") ?? "").trim();
  const api = getPortalApi();
  await api.createApprovalDecision(artifactId, {
    decision: decisionParam(String(formData.get("decision") ?? "")),
    reviewer: String(formData.get("reviewer") ?? ""),
    comment: String(formData.get("comment") ?? ""),
    validationReportId: validationReportId || undefined,
  });
  redirect(`/artifacts/${artifactId}`);
}

export default async function ReviewDecisionPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const params = await searchParams;
  const artifactId = firstParam(params.artifactId) ?? "";
  const decision = decisionParam(firstParam(params.decision));
  const reviewer = firstParam(params.reviewer) ?? "";
  const comment = firstParam(params.comment) ?? "P21 approval decision.";
  const requestedValidationReportId = firstParam(params.validationReportId);

  let artifact: Artifact | null = null;
  let validation: ValidationReport | null = null;
  if (artifactId) {
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

    const [artifactResult, validationResult] = await Promise.allSettled([
      api.getArtifact(artifactId),
      api.getLatestValidation(artifactId),
    ]);
    if (artifactResult.status === "rejected") {
      return (
        <div className="stack">
          <DependencyBlocker
            title="Artifact dependency is unavailable"
            message={formatPortalApiError(
              artifactResult.reason,
              "PLF artifact repository is required.",
            )}
            code={portalApiErrorCode(artifactResult.reason, "P21_REVIEW_ARTIFACT_BLOCKED")}
          />
        </div>
      );
    }
    artifact = artifactResult.value;
    validation = validationResult.status === "fulfilled" ? validationResult.value : null;
  }

  const validationReportId = requestedValidationReportId || validation?.validationReportId || "";

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Review boundary</p>
            <h1>Record decision</h1>
          </div>
          <span className="quiet-label">No publish action</span>
        </div>
        <p className="lede">
          This page records a reviewer decision through the API. It does not publish an artifact,
          deploy code, execute procedures, or apply DDL/DML.
        </p>
      </section>

      {artifact ? (
        <section className="split-layout">
          <div className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Artifact context</p>
                <h2>{artifact.title}</h2>
              </div>
              <StatusPill value={artifact.status} label={artifactStatusLabels[artifact.status]} />
            </div>
            <dl className="metric-grid metric-grid--compact">
              <div>
                <dt>Artifact</dt>
                <dd>{artifact.artifactId}</dd>
              </div>
              <div>
                <dt>Validation</dt>
                <dd>{validation ? validationStatusLabels[validation.status] : "Not recorded"}</dd>
              </div>
            </dl>

            {artifact.blockers?.length ? (
              <div className="blocker-list">
                {artifact.blockers.map((blocker) => (
                  <article className="blocker-row" key={blocker.code}>
                    <strong>{blocker.code}</strong>
                    <span>{blocker.message}</span>
                  </article>
                ))}
              </div>
            ) : null}
          </div>

          <div className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Validation gate</p>
                <h2>{validationReportId || "No validation report"}</h2>
              </div>
              <StatusPill
                value={validation?.status ?? "REVIEW_REQUIRED"}
                label={validation ? validationStatusLabels[validation.status] : "Not recorded"}
              />
            </div>
            <ul className="checklist">
              {validation?.manualReviewPoints?.map((point) => <li key={point}>{point}</li>)}
              <li>Publish remains unavailable from this UI.</li>
            </ul>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <form action={recordDecision} className="request-form">
          <div className="form-grid">
            <label>
              <span>Artifact id</span>
              <input name="artifactId" defaultValue={artifactId} required />
            </label>
            <label>
              <span>Validation report id</span>
              <input name="validationReportId" defaultValue={validationReportId} />
            </label>
            <label>
              <span>Decision</span>
              <select name="decision" defaultValue={decision}>
                {decisions.map((item) => (
                  <option key={item} value={item}>
                    {item.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Reviewer</span>
              <input name="reviewer" defaultValue={reviewer} required />
            </label>
          </div>

          <label>
            <span>Comment</span>
            <input name="comment" defaultValue={comment} required />
          </label>

          <div className="form-actions">
            <button type="submit">Record decision</button>
            {artifactId ? (
              <Link className="secondary-action" href={`/artifacts/${artifactId}`}>
                Return to artifact
              </Link>
            ) : (
              <Link className="secondary-action" href="/">
                Return to dashboard
              </Link>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}
