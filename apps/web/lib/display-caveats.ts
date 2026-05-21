import type { MetadataSearchBlocker, ValidationSeverity } from "@/lib/api/types";

export const DEPENDENCY_METADATA_INCOMPLETE = "DEPENDENCY_METADATA_INCOMPLETE";

export function displayRuleId(ruleId: string): string {
  return ruleId.replace(/review_required/gi, "evidence_caveat");
}

export function displayCaveatText(value: string): string {
  const text = value.trim();
  if (text === DEPENDENCY_METADATA_INCOMPLETE) {
    return "의존성 링크 일부는 근거 보강 필요 상태입니다. 확정 전까지 evidence caveat로 취급하세요.";
  }
  if (/^DEPENDENCY_METADATA_INCOMPLETE\b/i.test(text)) {
    return text.replace(
      /^DEPENDENCY_METADATA_INCOMPLETE\b:?\s*/i,
      "의존성 링크 일부는 근거 보강 필요 상태입니다. ",
    );
  }
  return text
    .replace(/^REVIEW_REQUIRED:\s*/i, "Evidence caveat: ")
    .replace(/review_required/gi, "evidence_caveat")
    .replace(/review\s+marker/gi, "evidence caveat");
}

export function displayArtifactContent(content: string): string {
  return content
    .replace(/\b([A-Z0-9]+(?:_[A-Z0-9]+)*)_REVIEW_REQUIRED\b/g, "$1_EVIDENCE_CAVEAT")
    .replace(/\b([A-Z0-9]+(?:_[A-Z0-9]+)*)_REVIEWMARKERS\b/g, "$1_EVIDENCE_CAVEATS")
    .replace(/\bLLM_INFERENCE_REVIEW_REQUIRED\b/g, "LLM_INFERENCE_EVIDENCE_CAVEAT")
    .replace(/\bREVIEW_REQUIRED\b:/g, "Evidence caveat:")
    .replace(/status=REVIEW_REQUIRED/g, "status=EVIDENCE_CAVEAT")
    .replace(/상태=REVIEW_REQUIRED/g, "상태=근거 보강 필요")
    .replace(/`REVIEW_REQUIRED`/g, "`Evidence caveat`")
    .replace(/\bREVIEW_REQUIRED\b/g, "Evidence caveat")
    .replace(/review\s+markers?/gi, "evidence caveats")
    .replace(/검토\s*마커/g, "근거 caveat")
    .replace(/검토\s*메모/g, "확인 메모")
    .replace(/결과\s*검토가\s*필요합니다/g, "근거 보강이 필요합니다")
    .replace(/ê²í \s*ë§ì»¤/g, "근거 caveat");
}

export function ruleLevelLabel(severity: ValidationSeverity): string {
  switch (severity) {
    case "BLOCKER":
    case "ERROR":
      return "Rule level: Required";
    case "WARNING":
      return "Rule level: Advisory";
    case "INFO":
      return "Rule level: Info";
  }
}

export function passedCheckLabel(severity: ValidationSeverity): string {
  switch (severity) {
    case "BLOCKER":
    case "ERROR":
      return "Passed required check";
    case "WARNING":
      return "Passed advisory check";
    case "INFO":
      return "Passed info check";
  }
}

export function isEvidenceCaveatCode(code: string): boolean {
  return code === DEPENDENCY_METADATA_INCOMPLETE;
}

export function splitMetadataBlockers(blockers: MetadataSearchBlocker[]): {
  caveatBlockers: MetadataSearchBlocker[];
  hardBlockers: MetadataSearchBlocker[];
} {
  const caveatBlockers: MetadataSearchBlocker[] = [];
  const hardBlockers: MetadataSearchBlocker[] = [];
  for (const blocker of blockers) {
    if (isEvidenceCaveatCode(blocker.code)) {
      caveatBlockers.push(blocker);
    } else {
      hardBlockers.push(blocker);
    }
  }
  return { caveatBlockers, hardBlockers };
}

export function metadataCaveatMessages(
  caveats: string[],
  blockers: MetadataSearchBlocker[] = [],
): string[] {
  return Array.from(
    new Set([
      ...caveats.map(displayCaveatText),
      ...blockers.filter((blocker) => isEvidenceCaveatCode(blocker.code)).map((blocker) =>
        displayCaveatText(blocker.code),
      ),
    ]),
  );
}
