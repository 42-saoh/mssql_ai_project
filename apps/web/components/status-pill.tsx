type Tone = "neutral" | "info" | "warning" | "success" | "danger";

const statusToneByValue: Record<string, Tone> = {
  SUBMITTED: "neutral",
  DRAFT: "neutral",
  COLLECTING_METADATA: "info",
  ANALYZING: "info",
  GENERATING: "info",
  VALIDATING: "warning",
  VALIDATED: "success",
  REVIEW_PENDING: "warning",
  REVIEW_REQUIRED: "warning",
  APPROVED: "success",
  APPROVE: "success",
  PASSED: "success",
  REJECTED: "danger",
  REJECT: "danger",
  REQUEST_CHANGES: "warning",
  FAILED: "danger",
  WARNING: "warning",
  INFO: "info",
  ERROR: "danger",
  FAIL: "danger",
  BLOCKER: "danger",
  CANCELED: "neutral",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};

export function StatusPill({
  value,
  label,
}: Readonly<{
  value: string;
  label: string;
}>) {
  const tone = statusToneByValue[value] ?? "neutral";

  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}
