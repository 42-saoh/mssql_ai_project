import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { MetadataSearchBlocker, MetadataSearchObjectType } from "@/lib/api/types";

const manifestRelativePath = path.join(
  "fixtures",
  "pilot",
  "ppm_object_selection_v1",
  "selected_objects.yaml",
);

export interface PilotMetadataObjectSample {
  id: string;
  schema: string;
  name: string;
  type: MetadataSearchObjectType;
  sourceProfile: string;
  sourceDatabase: string;
  snapshotId?: string;
  collectedAt?: string;
  evidenceLocator: string;
  caveats: string[];
  reviewRequired: boolean;
  blockers: MetadataSearchBlocker[];
  complexity?: string;
  parameterCount?: number;
  dependencyCount?: number;
  detectedPatterns?: string[];
  columnCount?: number;
}

export interface PilotManifestSummary {
  manifestPath: string;
  selectionMode: string;
  sourceDb: string;
  platformDbContext: string;
  generatedAt?: string;
  activeBlockers: MetadataSearchBlocker[];
  procedureSamples: PilotMetadataObjectSample[];
  metadataObjects: PilotMetadataObjectSample[];
}

function resolveManifestPath(): string {
  return path.join(
    /*turbopackIgnore: true*/ process.cwd(),
    "..",
    "..",
    "fixtures",
    "pilot",
    "ppm_object_selection_v1",
    "selected_objects.yaml",
  );
}

function cleanScalar(value: string | undefined): string {
  return (value ?? "")
    .trim()
    .replace(/^['"]/, "")
    .replace(/['"]$/, "");
}

function readScalar(text: string, key: string, fallback = ""): string {
  const match = text.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match ? cleanScalar(match[1]) : fallback;
}

function extractTopLevelSection(text: string, sectionName: string): string {
  const startPattern = new RegExp(`^${sectionName}:\\s*$`, "m");
  const startMatch = startPattern.exec(text);
  if (!startMatch) {
    return "";
  }

  const startIndex = startMatch.index + startMatch[0].length;
  const remaining = text.slice(startIndex);
  const nextMatch = /\n[a-zA-Z_][\w_]*:\s*$/m.exec(remaining);
  const endIndex = nextMatch ? startIndex + nextMatch.index : text.length;
  return text.slice(startIndex, endIndex);
}

function splitTopLevelItems(section: string): string[] {
  return section
    .split(/\n(?=  - )/)
    .map((item) => item.trimEnd())
    .filter((item) => item.trim().startsWith("- "));
}

function readIndentedScalar(block: string, key: string): string {
  const match = block.match(new RegExp(`^\\s+${key}:\\s*(.+)$`, "m"));
  return match ? cleanScalar(match[1]) : "";
}

function readIndentedNumber(block: string, key: string): number | undefined {
  const value = readIndentedScalar(block, key);
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function readIndentedBoolean(block: string, key: string, fallback: boolean): boolean {
  const value = readIndentedScalar(block, key);
  if (value === "true") {
    return true;
  }

  if (value === "false") {
    return false;
  }

  return fallback;
}

function readList(block: string, key: string): string[] {
  const lines = block.split("\n");
  const keyIndex = lines.findIndex((line) => line.trim() === `${key}:`);
  if (keyIndex === -1) {
    return [];
  }

  const keyIndent = lines[keyIndex].search(/\S/);
  const items: string[] = [];

  for (const line of lines.slice(keyIndex + 1)) {
    const indent = line.search(/\S/);
    if (indent !== -1 && indent <= keyIndent) {
      break;
    }

    const itemMatch = line.match(/^\s*-\s+(.+)$/);
    if (itemMatch) {
      items.push(cleanScalar(itemMatch[1]));
    }
  }

  return items;
}

function readActiveBlockers(text: string): MetadataSearchBlocker[] {
  return splitTopLevelItems(extractTopLevelSection(text, "active_blockers"))
    .map((block) => {
      const code = cleanScalar(block.match(/^\s*-\s+code:\s*(.+)$/m)?.[1]);
      const message = readIndentedScalar(block, "description");
      return code
        ? {
            code,
            message:
              message ||
              "Pilot metadata dependency is incomplete and must stay review-required.",
          }
        : null;
    })
    .filter((blocker): blocker is MetadataSearchBlocker => blocker !== null);
}

function objectLocator(sectionName: string, index: number): string {
  return `${manifestRelativePath}#/${sectionName}/${index}`;
}

function readObjectSection(
  text: string,
  sectionName: string,
  type: MetadataSearchObjectType,
  activeBlockers: MetadataSearchBlocker[],
): PilotMetadataObjectSample[] {
  return splitTopLevelItems(extractTopLevelSection(text, sectionName)).map((block, index) => {
    const schema = cleanScalar(block.match(/^\s*-\s+schema:\s*(.+)$/m)?.[1]);
    const name = readIndentedScalar(block, "name");
    const sourceDatabase = readIndentedScalar(block, "source_database") || readScalar(text, "source_db", "PPM");
    const snapshotId = readIndentedScalar(block, "snapshot_id");

    return {
      id: `${schema}.${name}`,
      schema,
      name,
      type,
      sourceProfile: readIndentedScalar(block, "source_profile") || "ppm",
      sourceDatabase,
      snapshotId,
      collectedAt: readIndentedScalar(block, "collected_at"),
      evidenceLocator: objectLocator(sectionName, index),
      caveats: readList(block, "caveats"),
      reviewRequired: readIndentedBoolean(block, "review_required", activeBlockers.length > 0),
      blockers: activeBlockers,
      complexity: readIndentedScalar(block, "complexity") || undefined,
      parameterCount: readIndentedNumber(block, "parameter_count"),
      dependencyCount: readIndentedNumber(block, "dependency_count"),
      detectedPatterns: readList(block, "detected_patterns"),
      columnCount: readIndentedNumber(block, "column_count"),
    };
  });
}

function templateOnlySummary(
  manifestPath: string,
  selectionMode = "template_only",
  activeBlockers: MetadataSearchBlocker[] = [],
): PilotManifestSummary {
  return {
    manifestPath,
    selectionMode,
    sourceDb: "PPM",
    platformDbContext: "PLF",
    activeBlockers: [
      {
        code: "PPM_MANIFEST_TEMPLATE_ONLY",
        message: "The PPM pilot manifest is template-only, so no real object names are displayed.",
      },
      ...activeBlockers,
    ],
    procedureSamples: [],
    metadataObjects: [],
  };
}

export function getPilotManifestSummary(): PilotManifestSummary {
  const manifestPath = resolveManifestPath();
  if (!existsSync(manifestPath)) {
    return templateOnlySummary(manifestPath, "missing");
  }

  const text = readFileSync(manifestPath, "utf-8");
  const selectionMode = readScalar(text, "selection_mode", "template_only");
  const activeBlockers = readActiveBlockers(text);
  if (selectionMode !== "live_metadata") {
    return templateOnlySummary(manifestPath, selectionMode, activeBlockers);
  }

  const procedures = readObjectSection(text, "stored_procedures", "PROCEDURE", activeBlockers);
  const tables = readObjectSection(text, "tables", "TABLE", activeBlockers);
  const views = readObjectSection(text, "views", "VIEW", activeBlockers);
  const functions = readObjectSection(text, "functions", "FUNCTION", activeBlockers);

  return {
    manifestPath,
    selectionMode,
    sourceDb: readScalar(text, "source_db", "PPM"),
    platformDbContext: readScalar(text, "platform_db_context", "PLF"),
    generatedAt: readScalar(text, "generated_at") || undefined,
    activeBlockers,
    procedureSamples: procedures,
    metadataObjects: [...procedures, ...tables, ...views, ...functions],
  };
}
