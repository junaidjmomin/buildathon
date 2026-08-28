import { beforeEach, describe, expect, it, vi } from "vitest";

type ActiveRunModule = typeof import("@/lib/active-run");

const run = (overrides: Partial<{ id: string; source_type: "DEMO" | "CSV_UPLOAD" | "RAZORPAY"; status: string }>) => ({
  id: "RUN_CSV_1",
  source_type: "CSV_UPLOAD" as const,
  status: "COMPLETE",
  ...overrides,
});

async function loadModule(): Promise<ActiveRunModule> {
  // The session override is module state; resetModules gives each test a
  // clean instance the same way a fresh browser session would.
  vi.resetModules();
  return import("@/lib/active-run");
}

describe("resolveActiveRun", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns undefined for an undefined or empty runs list", async () => {
    const { resolveActiveRun } = await loadModule();
    expect(resolveActiveRun(undefined, "RUN_1")).toBeUndefined();
    expect(resolveActiveRun([], null)).toBeUndefined();
  });

  it("prefers the explicit selection when it exists and is complete", async () => {
    const { resolveActiveRun } = await loadModule();
    const first = run({ id: "RUN_1" });
    const second = run({ id: "RUN_2" });
    expect(resolveActiveRun([first, second], "RUN_1")).toBe(first);
  });

  it("falls back to the latest real run when nothing is selected", async () => {
    const { resolveActiveRun } = await loadModule();
    const seeded = run({ id: "RUN_NOVACART", source_type: "DEMO" });
    const real = run({ id: "RUN_CSV_1" });
    expect(resolveActiveRun([seeded, real], null)).toBe(real);
  });

  it("never lets a stale stored seeded selection beat a real run", async () => {
    const { resolveActiveRun } = await loadModule();
    const seeded = run({ id: "RUN_NOVACART", source_type: "DEMO" });
    const real = run({ id: "RUN_CSV_1" });
    expect(resolveActiveRun([real, seeded], "RUN_NOVACART")).toBe(real);
  });

  it("keeps a seeded selection when the session explicitly allows it", async () => {
    const { resolveActiveRun } = await loadModule();
    const seeded = run({ id: "RUN_NOVACART", source_type: "DEMO" });
    const real = run({ id: "RUN_CSV_1" });
    expect(resolveActiveRun([real, seeded], "RUN_NOVACART", { allowSeeded: true })).toBe(seeded);
  });

  it("keeps a seeded selection on a tenant with no real runs", async () => {
    const { resolveActiveRun } = await loadModule();
    const seeded = run({ id: "RUN_NOVACART", source_type: "DEMO" });
    expect(resolveActiveRun([seeded], "RUN_NOVACART")).toBe(seeded);
  });

  it("ignores a selection that is not complete and falls back to a real run", async () => {
    const { resolveActiveRun } = await loadModule();
    const running = run({ id: "RUN_RUNNING", status: "RUNNING" });
    const real = run({ id: "RUN_CSV_1" });
    expect(resolveActiveRun([running, real], "RUN_RUNNING")).toBe(real);
  });

  it("ignores a selection that no longer exists", async () => {
    const { resolveActiveRun } = await loadModule();
    const real = run({ id: "RUN_CSV_1" });
    expect(resolveActiveRun([real], "RUN_DELETED")).toBe(real);
  });
});

describe("setActiveRunId", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("persists durable selections to localStorage and clears the override", async () => {
    const { setActiveRunId, readActiveRunId, readActiveRunIsOverride } = await loadModule();
    setActiveRunId("RUN_NOVACART", { persist: false });
    setActiveRunId("RUN_CSV_1", { persist: true });
    expect(window.localStorage.getItem("sl3dge.active-run-id")).toBe("RUN_CSV_1");
    expect(readActiveRunId()).toBe("RUN_CSV_1");
    expect(readActiveRunIsOverride()).toBe(false);
  });

  it("keeps seeded selections session-scoped without touching storage", async () => {
    const { setActiveRunId, readActiveRunId, readActiveRunIsOverride } = await loadModule();
    window.localStorage.setItem("sl3dge.active-run-id", "RUN_CSV_1");
    setActiveRunId("RUN_NOVACART", { persist: false });
    expect(window.localStorage.getItem("sl3dge.active-run-id")).toBe("RUN_CSV_1");
    expect(readActiveRunId()).toBe("RUN_NOVACART");
    expect(readActiveRunIsOverride()).toBe(true);
  });

  it("notifies listeners through the run-changed event", async () => {
    const { setActiveRunId } = await loadModule();
    const listener = vi.fn();
    window.addEventListener("sl3dge:active-run-changed", listener);
    setActiveRunId("RUN_CSV_2");
    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0]?.[0] as CustomEvent).detail).toBe("RUN_CSV_2");
    window.removeEventListener("sl3dge:active-run-changed", listener);
  });
});

describe("useActiveRunId", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("reads the stored selection after mount and reacts to changes", async () => {
    const { renderHook, act, waitFor } = await import("@testing-library/react");
    const { setActiveRunId, useActiveRunId } = await loadModule();
    window.localStorage.setItem("sl3dge.active-run-id", "RUN_CSV_1");

    const { result } = renderHook(() => useActiveRunId());
    await waitFor(() => expect(result.current).toBe("RUN_CSV_1"));

    act(() => setActiveRunId("RUN_CSV_2", { persist: false }));
    await waitFor(() => expect(result.current).toBe("RUN_CSV_2"));
  });
});
