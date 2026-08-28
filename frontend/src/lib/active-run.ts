"use client";

import { useEffect, useState } from "react";

const ACTIVE_RUN_KEY = "sl3dge.active-run-id";
const ACTIVE_RUN_EVENT = "sl3dge:active-run-changed";

// A seeded demo selection is session-scoped only. Persisting it made the
// NovaCart demo resurface as the default workspace on every fresh page load,
// even after real uploaded runs existed.
let sessionOverride: string | null = null;

export function readActiveRunId(): string | null {
  if (sessionOverride) {
    return sessionOverride;
  }
  return typeof window === "undefined" ? null : window.localStorage.getItem(ACTIVE_RUN_KEY);
}

export function readActiveRunIsOverride(): boolean {
  return sessionOverride !== null;
}

export function setActiveRunId(runId: string, options?: { persist?: boolean }): void {
  const persist = options?.persist !== false;
  if (persist) {
    window.localStorage.setItem(ACTIVE_RUN_KEY, runId);
    sessionOverride = null;
  } else {
    sessionOverride = runId;
  }
  window.dispatchEvent(new CustomEvent(ACTIVE_RUN_EVENT, { detail: runId }));
}

export function useActiveRunId(): string | null {
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => setRunId(readActiveRunId());
    refresh();
    window.addEventListener(ACTIVE_RUN_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(ACTIVE_RUN_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  return runId;
}

export function useActiveRunOverride(): boolean {
  const [isOverride, setIsOverride] = useState(false);

  useEffect(() => {
    const refresh = () => setIsOverride(readActiveRunIsOverride());
    refresh();
    window.addEventListener(ACTIVE_RUN_EVENT, refresh);
    return () => {
      window.removeEventListener(ACTIVE_RUN_EVENT, refresh);
    };
  }, []);

  return isOverride;
}

type RunLike = { id: string; source_type: "DEMO" | "CSV_UPLOAD" | "RAZORPAY"; status: string };

/**
 * Resolve the run a page should display.
 *
 * Priority: an explicit selection that still exists, then the latest real
 * (non-seeded) completed run. A seeded selection only wins when it is the
 * current session's explicit choice (or the tenant has no real runs at all),
 * so a stale stored demo never overrides real uploaded data.
 */
export function resolveActiveRun<T extends RunLike>(
  runs: T[] | undefined,
  selectedRunId: string | null,
  options?: { allowSeeded?: boolean },
): T | undefined {
  if (!runs) {
    return undefined;
  }
  const selected = runs.find((run) => run.id === selectedRunId && run.status === "COMPLETE");
  const latestReal = runs.find((run) => run.source_type !== "DEMO" && run.status === "COMPLETE");
  if (!latestReal) {
    return selected;
  }
  if (selected?.source_type === "DEMO" && !options?.allowSeeded) {
    return latestReal;
  }
  return selected ?? latestReal;
}
