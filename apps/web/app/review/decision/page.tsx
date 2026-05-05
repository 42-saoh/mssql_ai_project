import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import { getPortalApi } from "@/lib/api/client";
import type { ApprovalDecision } from "@/lib/api/types";
import { artifactStatusLabels, validationStatusLabels } from "@/lib/presentation";

const decisions: ApprovalDecision[] = ["REQUEST_CHANGES", "APPROVE", "REJECT"];

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function decisionParam(value: string | undefined): ApprovalDecision {
  return decisions.includes(value as ApprovalDecision)
    ? (value as ApprovalDecision)
    : "REQUEST_CHANGES";
}

export default async function ReviewDecisionPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const params = await searchParams;
  const api = getPortalApi();
  const artifactId = firstParam(params.artifactId) ?? "art_demo_sp_analysis";
  const decision = decisionParam(firstParam(params.decision));
  const reviewer = firstParam(params.reviewer) ?? "reviewer@example.com";
  const comment =
    firstParam(params.comment) ??
    "Preview only: dependency blocker remains open and publish is unavailable.";
  const requestedValidationReportId = firstParam(params.validationReportId);
  const [artifact, validation] = await Promise.all([
    api.getArtifact(artifactId),
    api.validateArtifact(artifactId),
  ]);
  const validationReportId = requestedValidationReportId || `validation_preview_${artifactId}`;
  const approvalPreview = {
    approvalId: `approval_preview_${artifactId}`,
    artifactId,
    decision,
    reviewer,
    comment,
    validationReportId,
    persisted: false,
    publishesArtifact: false,
    executesDeployment: false,
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Review boundary</p>
            <h1>Decision preview</h1>
          </div>
          <span className="quiet-label">No publish action</span>
        </div>
        <p className="lede">
          Shape the approval decision payload a reviewer would record. This page does not call the
          approval endpoint, publish an artifact, deploy code, execute procedures, or apply DDL.
        </p>
      </section>

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
              <dd>{validationStatusLabels[validation.status]}</dd>
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
              <h2>{validationReportId}</h2>
            </div>
            <StatusPill value={validation.status} label={validationStatusLabels[validation.status]} />
          </div>
          <ul className="checklist">
            {validation.manualReviewPoints?.map((point) => <li key={point}>{point}</li>)}
            <li>Publish remains unavailable from this UI.</li>
          </ul>
        </div>
      </section>

      <section className="panel">
        <form className="request-form" method="get">
          <div className="form-grid">
            <label>
              <span>Artifact id</span>
              <input name="artifactId" defaultValue={artifactId} />
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
              <input name="reviewer" defaultValue={reviewer} />
            </label>
          </div>

          <label>
            <span>Comment</span>
            <input name="comment" defaultValue={comment} />
          </label>

          <div className="form-actions">
            <button type="submit">Preview decision record</button>
            <Link className="secondary-action" href={`/artifacts/${artifactId}`}>
              Return to artifact
            </Link>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Preview record</p>
            <h2>{approvalPreview.approvalId}</h2>
          </div>
          <StatusPill value={approvalPreview.decision} label={approvalPreview.decision.replace("_", " ")} />
        </div>
        <div className="content-preview" aria-label="Approval decision preview">
          <pre>{JSON.stringify(approvalPreview, null, 2)}</pre>
        </div>
      </section>
    </div>
  );
}
