import Link from "next/link";
import { StatusPill } from "@/components/status-pill";
import type { ArtifactSummary, Job } from "@/lib/api/types";
import {
  artifactStatusLabels,
  artifactTypeLabels,
  formatCoverage,
  jobStatusLabels,
  workflowStepLabels,
} from "@/lib/presentation";

const stageLinks = [
  { href: "/jobs/job_demo_draft", label: "draft" },
  { href: "/jobs/job_demo_validating", label: "validating" },
  { href: "/jobs/job_demo_review_pending", label: "review_pending" },
  { href: "/jobs/job_demo_approved", label: "approved" },
  { href: "/jobs/job_demo_rejected", label: "rejected" },
];

const workflowSteps = [
  "COLLECT_METADATA",
  "ANALYZE",
  "GENERATE",
  "VALIDATE",
  "REVIEW",
] as const;

function stepState(job: Job, step: (typeof workflowSteps)[number]) {
  if (job.status === "APPROVED" || job.status === "REJECTED") {
    return "done";
  }

  if (job.currentStep === step) {
    return "current";
  }

  const currentIndex = job.currentStep
    ? workflowSteps.findIndex((workflowStep) => workflowStep === job.currentStep)
    : -1;
  const stepIndex = workflowSteps.indexOf(step);

  return currentIndex > stepIndex ? "done" : "pending";
}

export function JobStatusView({
  job,
  scenarioSummary,
  artifacts,
}: Readonly<{
  job: Job;
  scenarioSummary: string;
  artifacts: ArtifactSummary[];
}>) {
  return (
    <div className="stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Workflow job</p>
            <h1>{job.jobId}</h1>
          </div>
          <StatusPill value={job.status} label={jobStatusLabels[job.status]} />
        </div>

        <p className="lede">{scenarioSummary}</p>

        <dl className="metric-grid">
          <div>
            <dt>Request</dt>
            <dd>{job.requestId}</dd>
          </div>
          <div>
            <dt>Current step</dt>
            <dd>{job.currentStep ? workflowStepLabels[job.currentStep] : "Draft intake"}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{job.updatedAt ?? "Not available"}</dd>
          </div>
        </dl>

        <div className="stage-link-row" aria-label="Mock job status examples">
          {stageLinks.map((stage) => (
            <Link key={stage.href} href={stage.href}>
              {stage.label}
            </Link>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Approval-gated flow</p>
            <h2>Draft to review status</h2>
          </div>
        </div>
        <ol className="timeline">
          {workflowSteps.map((step) => (
            <li className={`timeline-step timeline-step--${stepState(job, step)}`} key={step}>
              <span>{workflowStepLabels[step]}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Draft artifacts</p>
            <h2>Preview outputs</h2>
          </div>
          <span className="quiet-label">Mock adapter</span>
        </div>

        <div className="artifact-list">
          {artifacts.map((artifact) => (
            <article className="artifact-row" key={artifact.artifactId}>
              <div>
                <h3>{artifact.title ?? artifactTypeLabels[artifact.type]}</h3>
                <p>
                  {artifactTypeLabels[artifact.type]} · evidence coverage{" "}
                  {formatCoverage(artifact.evidenceCoverage)}
                </p>
              </div>
              <div className="row-actions">
                <StatusPill
                  value={artifact.status}
                  label={artifactStatusLabels[artifact.status]}
                />
                <Link href={`/artifacts/${artifact.artifactId}`}>Preview</Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
