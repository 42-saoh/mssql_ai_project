"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { JobStatus } from "@/lib/api/types";

const terminalStatuses: ReadonlySet<JobStatus> = new Set([
  "VALIDATION_COMPLETE",
  "FAILED",
  "CANCELED",
]);

export function JobAutoRefresh({
  status,
  intervalMs = 1500,
}: Readonly<{
  status: JobStatus;
  intervalMs?: number;
}>) {
  const router = useRouter();
  const active = !terminalStatuses.has(status);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      router.refresh();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs, router]);

  if (!active) {
    return null;
  }

  return (
    <span className="quiet-label" aria-live="polite">
      작업 진행 중 - 자동 새로고침 중
    </span>
  );
}
