"use client";

import {
  Boxes,
  FileCheck2,
  Gauge,
  GitBranch,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/components/auth-provider";
import {
  resolveActiveRun,
  setActiveRunId,
  useActiveRunId,
  useActiveRunOverride,
} from "@/lib/active-run";
import { api } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const isNavigating = pendingHref !== null && pendingHref !== pathname;
  const auth = useAuth();
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const items = [
    { label: "Overview", icon: LayoutDashboard, href: "/" },
    { label: "Controls", icon: ShieldCheck, href: "/controls" },
    { label: "Exceptions", icon: TriangleAlert, href: "/exceptions" },
    { label: "Root causes", icon: GitBranch, href: "/root-causes" },
    { label: "Agreements", icon: FileCheck2, href: "/agreements" },
    { label: "Data sources", icon: Boxes, href: "/data" },
  ];
  // Warm the destination page's primary query when the user signals intent
  // (hover or keyboard focus) so the first paint of that tab has data.
  const prefetchTarget = useCallback(
    (href: string) => {
      if (!activeRun) return;
      const runId = activeRun.id;
      if (href === "/") {
        void queryClient.prefetchQuery({
          queryKey: ["run-summary", runId],
          queryFn: () => api.summary(runId),
        });
      } else if (href === "/controls") {
        void queryClient.prefetchQuery({ queryKey: ["controls"], queryFn: api.controls });
      } else if (href === "/exceptions") {
        void queryClient.prefetchQuery({
          queryKey: ["exception-cases", runId],
          queryFn: () => api.exceptionCases(runId),
        });
      } else if (href === "/root-causes") {
        void queryClient.prefetchQuery({
          queryKey: ["root-causes", runId],
          queryFn: () => api.rootCauses(runId),
        });
      } else if (href === "/agreements") {
        void queryClient.prefetchQuery({ queryKey: ["agreements"], queryFn: api.agreements });
      }
    },
    [activeRun, queryClient],
  );
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      {isNavigating ? (
        <div aria-label="Loading page" className="fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden bg-[var(--line-strong)]">
          <div className="h-full w-2/3 animate-pulse bg-[var(--evergreen)]" />
        </div>
      ) : null}
      <aside className="hidden min-h-screen flex-col border-r border-[var(--line)] bg-[var(--ink-700)] px-4 py-5 lg:flex">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-[rgba(47,189,127,0.16)] text-[var(--evergreen)]">
            <Gauge size={20} strokeWidth={2.4} />
          </span>
          <span>
            <span className="block text-[21px] font-semibold leading-5 tracking-[-0.04em] text-[var(--paper)]">sl3dge</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--paper-faint)]">Control engine</span>
          </span>
        </Link>
        <nav className="space-y-1">
          {items.map(({ label, icon: Icon, href }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={label}
                href={href ?? "#"}
                onClick={() => { if (href !== pathname) setPendingHref(href); }}
                onFocus={() => prefetchTarget(href)}
                onMouseEnter={() => prefetchTarget(href)}
                className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] transition-colors duration-150 ${
                  active
                    ? "bg-[rgba(47,189,127,0.12)] font-medium text-[var(--paper)]"
                    : "text-[var(--paper-dim)] hover:bg-white/[0.04] hover:text-[var(--paper)]"
                }`}
                aria-current={active ? "page" : undefined}
              >
                {active ? (
                  <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-[var(--evergreen)]" />
                ) : null}
                <Icon size={16} className={active ? "text-[var(--evergreen)]" : ""} /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-xl border border-[var(--line)] bg-[rgba(47,189,127,0.05)] p-3.5">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[var(--paper)]">
            <Sparkles size={14} className="text-[var(--evergreen)]" /> Verification principle
          </div>
          <p className="text-[11px] leading-5 text-[var(--paper-dim)]">AI proposes. Controls calculate. Evidence decides.</p>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-[var(--line)] bg-[rgba(10,18,16,0.85)] px-5 backdrop-blur-xl md:px-8">
          <div className="flex items-center gap-2 text-xs text-[var(--paper-dim)]">
            <ShieldCheck size={15} className="text-[var(--evergreen)]" />
            <span className="font-medium text-[var(--paper)]">Financial controls</span>
            <span>·</span>
            {runs.data && runs.data.length > 0 ? (
              <label className="sr-only" htmlFor="active-run">Active run</label>
            ) : null}
            {runs.data && runs.data.length > 0 ? (
              <select
                id="active-run"
                value={activeRun?.id ?? ""}
                onChange={(event) => {
                  const run = runs.data?.find((item) => item.id === event.currentTarget.value);
                  // Seeded demo selections stay session-scoped so they never
                  // become the default workspace on the next page load.
                  setActiveRunId(event.currentTarget.value, {
                    persist: run?.source_type !== "DEMO",
                  });
                }}
                className="max-w-56 cursor-pointer bg-[var(--ink-700)] font-medium text-[var(--paper)] outline-none"
                style={{ colorScheme: "dark" }}
              >
                <option value="" className="bg-[var(--ink-700)] text-[var(--paper)]">Select a run</option>
                {runs.data.map((run) => (
                  <option key={run.id} value={run.id} className="bg-[var(--ink-700)] text-[var(--paper)]">
                    {run.name} · {run.source_type.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            ) : (
              <span>No active run</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {auth.enabled ? (
              <span className="hidden max-w-44 truncate text-[11px] font-medium text-[var(--paper-dim)] sm:inline">
                {auth.displayName}
              </span>
            ) : null}
            <div className="flex items-center gap-2 rounded-full border border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.08)] px-3 py-1.5 text-[11px] font-medium text-[var(--evergreen)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--evergreen)]" /> Verification-first
            </div>
            {auth.enabled ? (
              <button
                aria-label="Sign out"
                className="grid h-8 w-8 place-items-center rounded-full border border-[var(--line-strong)] text-[var(--paper-dim)] transition-colors hover:text-[var(--paper)]"
                onClick={() => void auth.signOut()}
                title="Sign out"
                type="button"
              >
                <LogOut aria-hidden="true" size={14} />
              </button>
            ) : null}
          </div>
        </header>
        <nav
          aria-label="Primary navigation"
          className="sticky top-16 z-10 flex gap-1 overflow-x-auto border-b border-[var(--line)] bg-[var(--ink-800)] px-3 py-2 lg:hidden"
        >
          {items.map(({ label, icon: Icon, href }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={label}
                href={href}
                onClick={() => { if (href !== pathname) setPendingHref(href); }}
                onFocus={() => prefetchTarget(href)}
                onMouseEnter={() => prefetchTarget(href)}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${
                  active ? "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]" : "text-[var(--paper-dim)]"
                }`}
              >
                <Icon size={14} /> {label}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </div>
  );
}
