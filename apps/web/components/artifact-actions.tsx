"use client";

import { useState } from "react";

export function ArtifactActions({
  artifactId,
  content,
}: Readonly<{
  artifactId: string;
  content: string;
}>) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "blocked">("idle");

  async function copyContent() {
    try {
      await navigator.clipboard.writeText(content);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2200);
    } catch {
      setCopyState("blocked");
    }
  }

  return (
    <div className="artifact-action-row">
      <button type="button" onClick={copyContent}>
        Copy content
      </button>
      <a className="secondary-action" href={`/artifacts/${encodeURIComponent(artifactId)}/download`}>
        Download draft file
      </a>
      <span className="copy-status" aria-live="polite">
        {copyState === "copied"
          ? "Copied"
          : copyState === "blocked"
            ? "Clipboard unavailable"
            : "Draft content only"}
      </span>
    </div>
  );
}
