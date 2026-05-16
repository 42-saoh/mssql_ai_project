import type {
  ArtifactStatus,
  ArtifactType,
  JobStatus,
  RequestedOutputType,
  ValidationStatus,
  WorkflowStepType,
} from "./api/types";

export const outputLabels: Record<RequestedOutputType, string> = {
  SP_ANALYSIS_DOCUMENT: "SP analysis document",
  DEPENDENCY_REPORT: "Dependency report",
  TABLE_COLUMN_METADATA: "Table/column metadata",
  JAVA_MYBATIS_DRAFT: "Java/MyBatis draft",
  DTO_MODEL_DRAFT: "DTO/model draft",
  DDL_DRAFT: "DDL draft file",
};

export const outputDescriptions: Record<RequestedOutputType, string> = {
  SP_ANALYSIS_DOCUMENT: "Procedure summary, behavior notes, assumptions, and evidence references.",
  DEPENDENCY_REPORT: "Procedure, table, view, function, and call relationship preview.",
  TABLE_COLUMN_METADATA: "Read-only metadata shape needed for field and result set caveats.",
  JAVA_MYBATIS_DRAFT: "Mapper XML, mapper interface, and service draft grouping.",
  DTO_MODEL_DRAFT: "DTO/VO/model draft grouping with evidence caveats.",
  DDL_DRAFT: "Draft SQL file; no execution path is exposed.",
};

export const requestedOutputOptions: RequestedOutputType[] = [
  "SP_ANALYSIS_DOCUMENT",
  "DEPENDENCY_REPORT",
  "JAVA_MYBATIS_DRAFT",
  "DTO_MODEL_DRAFT",
  "DDL_DRAFT",
];

export const jobStatusLabels: Record<JobStatus, string> = {
  SUBMITTED: "Draft",
  COLLECTING_METADATA: "Collecting metadata",
  ANALYZING: "Analyzing",
  GENERATING: "Generating",
  VALIDATING: "Validating",
  VALIDATION_COMPLETE: "Validation complete",
  FAILED: "Failed",
  CANCELED: "Canceled",
};

export const workflowStepLabels: Record<WorkflowStepType, string> = {
  COLLECT_METADATA: "Collect metadata",
  ANALYZE: "Analyze",
  GENERATE: "Generate",
  VALIDATE: "Validate",
};

export const artifactTypeLabels: Record<ArtifactType, string> = {
  SP_ANALYSIS_DOC: "SP analysis doc",
  DEPENDENCY_REPORT: "Dependency report",
  METADATA_QUERY_RESULT: "Metadata result",
  SCHEMA_ENRICHMENT_RESULT: "Schema enrichment",
  MAPPER_XML: "Mapper XML",
  MAPPER_INTERFACE: "Mapper interface",
  SERVICE_DRAFT: "Service draft",
  DTO_DRAFT: "DTO draft",
  VO_DRAFT: "VO draft",
  MODEL_DRAFT: "Model draft",
  DDL_DRAFT: "DDL draft",
  VALIDATION_REPORT: "Validation report",
};

export const artifactStatusLabels: Record<ArtifactStatus, string> = {
  DRAFT: "Draft",
  VALIDATED: "Validated",
  ARCHIVED: "Archived",
};

export const validationStatusLabels: Record<ValidationStatus, string> = {
  PASSED: "Passed",
  FAILED: "Failed",
  REVIEW_REQUIRED: "Evidence caveat",
};

export function formatCoverage(value?: number): string {
  if (value === undefined) {
    return "Not measured";
  }

  return `${Math.round(value * 100)}%`;
}

export function jobStatusSummary(status: JobStatus): string {
  switch (status) {
    case "SUBMITTED":
    case "COLLECTING_METADATA":
    case "ANALYZING":
    case "GENERATING":
      return "The request is still in a draft generation phase before validation completes.";
    case "VALIDATING":
      return "Generated drafts are passing through evidence and policy checks.";
    case "VALIDATION_COMPLETE":
      return "Validation is complete for the draft artifacts. No approval or publish action is exposed.";
    case "FAILED":
      return "The workflow failed and requires operator inspection.";
    case "CANCELED":
      return "The workflow was canceled before validation completed.";
  }
}
