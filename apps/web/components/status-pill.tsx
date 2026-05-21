type Tone = "neutral" | "info" | "warning" | "success" | "danger";

const statusToneByValue: Record<string, Tone> = {
  SUBMITTED: "neutral",
  DRAFT: "neutral",
  COLLECTING_METADATA: "info",
  ANALYZING: "info",
  GENERATING: "info",
  VALIDATING: "warning",
  VALIDATION_COMPLETE: "success",
  VALIDATED: "success",
  REVIEW_REQUIRED: "warning",
  PASSED: "success",
  FAILED: "danger",
  WARNING: "warning",
  INFO: "info",
  ERROR: "danger",
  FAIL: "danger",
  BLOCKER: "danger",
  CANCELED: "neutral",
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
