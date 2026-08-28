"use client";

import { useEffect, useState } from "react";

const ACTIVE_RUN_KEY = "sl3dge.active-run-id";
const ACTIVE_RUN_EVENT = "sl3dge:active-run-changed";

export function readActiveRunId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(ACTIVE_RUN_KEY);
}

export function setActiveRunId(runId: string): void {
  window.localStorage.setItem(ACTIVE_RUN_KEY, runId);
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
