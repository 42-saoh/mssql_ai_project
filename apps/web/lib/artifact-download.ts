import type { Artifact, ArtifactSummary, ArtifactType } from "@/lib/api/types";

const extensionByType: Partial<Record<ArtifactType, string>> = {
  SP_ANALYSIS_DOC: "md",
  DEPENDENCY_REPORT: "md",
  METADATA_QUERY_RESULT: "json",
  SCHEMA_ENRICHMENT_RESULT: "json",
  MAPPER_XML: "xml",
  MAPPER_INTERFACE: "java",
  SERVICE_DRAFT: "java",
  DTO_DRAFT: "java",
  VALIDATION_REPORT: "json",
};

const contentTypeByExtension: Record<string, string> = {
  java: "text/plain; charset=utf-8",
  json: "application/json; charset=utf-8",
  md: "text/markdown; charset=utf-8",
  sql: "text/plain; charset=utf-8",
  txt: "text/plain; charset=utf-8",
  xml: "application/xml; charset=utf-8",
};

export function artifactFileExtension(type: ArtifactType): string {
  return extensionByType[type] ?? "txt";
}

export function artifactContentType(type: ArtifactType): string {
  return contentTypeByExtension[artifactFileExtension(type)] ?? contentTypeByExtension.txt;
}

export function sanitizeFilePart(value: string): string {
  const sanitized = value
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return sanitized || "draft";
}

export function artifactFilename(
  artifact: Pick<Artifact | ArtifactSummary, "artifactId" | "type" | "title">,
  index?: number,
): string {
  const prefix = index === undefined ? "" : `${String(index).padStart(2, "0")}-`;
  const label = sanitizeFilePart(artifact.title ?? artifact.type);
  const artifactId = sanitizeFilePart(artifact.artifactId);
  return `${prefix}${label}-${artifactId}.${artifactFileExtension(artifact.type)}`;
}
