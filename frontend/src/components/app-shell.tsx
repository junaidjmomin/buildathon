"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Boxes,
  FileCheck2,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { BrandMark } from "@/components/brand-assets";
import {
  resolveActiveRun,
  setActiveRunId,
  useActiveRunId,
  useActiveRunOverride,
} from "@/lib/active-run";
import { api } from "@/lib/api";

const NAV_GROUPS = [
  {
    label: "Monitor",
    items: [
      { label: "Overview", icon: LayoutDashboard, href: "/" },
      { label: "Exceptions", icon: TriangleAlert, href: "/exceptions" },
      { label: "Root causes", icon: GitBranch, href: "/root-causes" },
    ],
  },
  {
    label: "Governance",
    items: [
      { label: "Controls", icon: ShieldCheck, href: "/controls" },
      { label: "Agreements", icon: FileCheck2, href: "/agreements" },
    ],
  },
  {
    label: "Workspace",
    items: [{ label: "Data sources", icon: Boxes, href: "/data" }],
  },
] as const;

function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link
      aria-label="sl3dge overview"
      className="flex min-w-0 items-center gap-3 rounded-md"
      href="/"
    >
      <span
        className={`grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-[9px] border ${
          dark
            ? "border-[var(--nav-line)] bg-[var(--nav-800)]"
            : "border-[var(--line)] bg-[var(--ink-700)]"
        }`}
      >
        <BrandMark className="h-8 w-8 object-contain" size={32} />
      </span>
      <span className="min-w-0">
        <span
          className={`block text-[20px] font-semibold leading-5 tracking-[-0.045em] ${
            dark ? "text-[var(--nav-text)]" : "text-[var(--paper)]"
          }`}
        >
          sl3dge
        </span>
        <span
          className={`mt-1 block truncate text-[9px] font-medium uppercase tracking-[0.16em] ${
            dark ? "text-[var(--nav-muted)]" : "text-[var(--paper-faint)]"
          }`}
        >
          Financial evidence
        </span>
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const mobileNavigationTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileNavigationRef = useRef<HTMLElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const isNavigating = pendingHref !== null && pendingHref !== pathname;
  const auth = useAuth();
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });

  useEffect(() => {
    const resetNavigation = window.setTimeout(() => setMobileNavigationOpen(false), 0);
    return () => window.clearTimeout(resetNavigation);
  }, [pathname]);

  useEffect(() => {
    if (!mobileNavigationOpen) return;

    const previousOverflow = document.body.style.overflow;
    const navigationTrigger = mobileNavigationTriggerRef.current;
    const containKeyboardFocus = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileNavigationOpen(false);
        return;
      }
      if (event.key !== "Tab" || !mobileNavigationRef.current) return;

      const focusable = Array.from(
        mobileNavigationRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", containKeyboardFocus);
    mobileCloseRef.current?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", containKeyboardFocus);
      navigationTrigger?.focus();
    };
  }, [mobileNavigationOpen]);

  // Warm each destination's primary data when the user signals intent.
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

  const selectRun = (runId: string) => {
    const run = runs.data?.find((item) => item.id === runId);
    // Seeded demo selections stay session-scoped so they never become the
    // default workspace on the next page load.
    setActiveRunId(runId, { persist: run?.source_type !== "DEMO" });
  };

  const runPicker = (id: string, dark = false) => (
    <div className="min-w-0">
      <label
        className={`mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] ${
          dark ? "text-[var(--nav-muted)]" : "text-[var(--paper-faint)]"
        }`}
        htmlFor={id}
      >
        Control run
      </label>
      {runs.data && runs.data.length > 0 ? (
        <select
          className={`h-9 w-full min-w-0 cursor-pointer rounded-md border px-3 pr-8 text-xs font-medium outline-none transition-colors ${
            dark
              ? "border-[var(--nav-line)] bg-[var(--nav-800)] text-[var(--nav-text)]"
              : "border-[var(--line)] bg-[var(--ink-800)] text-[var(--paper)] hover:border-[var(--line-strong)]"
          }`}
          id={id}
          onChange={(event) => selectRun(event.currentTarget.value)}
          value={activeRun?.id ?? ""}
        >
          <option value="">Select a run</option>
          {runs.data.map((run) => (
            <option key={run.id} value={run.id}>
              {run.name} · {run.source_type.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      ) : (
        <p className={`text-xs ${dark ? "text-[var(--nav-muted)]" : "text-[var(--paper-dim)]"}`}>
          No active run
        </p>
      )}
    </div>
  );

  const navigation = (mobile = false) => (
    <nav aria-label="Primary navigation" className="space-y-6">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-2 px-3 text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--nav-muted)]">
            {group.label}
          </p>
          <div className="space-y-1">
            {group.items.map(({ label, icon: Icon, href }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={`group relative flex min-h-10 w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-[13px] font-medium transition-colors ${
                    active
                      ? "bg-[var(--nav-active)] text-[var(--nav-text)]"
                      : "text-[var(--nav-muted)] hover:bg-[var(--nav-800)] hover:text-[var(--nav-text)]"
                  }`}
                  href={href}
                  key={label}
                  onClick={() => {
                    if (href !== pathname) setPendingHref(href);
                    if (mobile) setMobileNavigationOpen(false);
                  }}
                  onFocus={() => prefetchTarget(href)}
                  onMouseEnter={() => prefetchTarget(href)}
                >
                  {active ? (
                    <span
                      aria-hidden="true"
                      className="absolute inset-y-2 left-0 w-0.5 bg-[var(--nav-accent)]"
                    />
                  ) : null}
                  <Icon
                    aria-hidden="true"
                    className={
                      active
                        ? "text-[var(--nav-accent)]"
                        : "transition-colors group-hover:text-[var(--nav-text)]"
                    }
                    size={16}
                    strokeWidth={1.9}
                  />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      {isNavigating ? (
        <div
          aria-label="Loading page"
          aria-live="polite"
          className="fixed inset-x-0 top-0 z-[70] h-0.5 overflow-hidden bg-[var(--line)]"
          role="status"
        >
          <div className="h-full w-1/2 animate-pulse bg-[var(--evergreen)]" />
        </div>
      ) : null}

      <aside className="hidden h-screen flex-col border-r border-[var(--nav-line)] bg-[var(--nav-900)] px-3 py-5 lg:sticky lg:top-0 lg:flex">
        <div className="px-2">
          <Brand dark />
        </div>
        <div className="mt-9">{navigation()}</div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[color:rgba(255,254,250,0.96)] backdrop-blur-md">
          <div className="flex h-16 items-center justify-between gap-4 px-4 md:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3 lg:hidden">
              <button
                aria-controls="mobile-navigation"
                aria-expanded={mobileNavigationOpen}
                aria-label="Open navigation"
                className="mobile-nav-trigger grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[var(--line)] transition-colors"
                onClick={() => setMobileNavigationOpen(true)}
                ref={mobileNavigationTriggerRef}
                type="button"
              >
                <Menu aria-hidden="true" size={18} />
              </button>
              <Brand />
            </div>

            <div className="hidden w-full max-w-sm lg:block">{runPicker("active-run-desktop")}</div>

            <div className="ml-auto flex min-w-0 items-center gap-2">
              {auth.enabled ? (
                <span className="hidden max-w-48 truncate text-xs font-medium text-[var(--paper-dim)] sm:inline">
                  {auth.displayName}
                </span>
              ) : null}
              {auth.enabled ? (
                <button
                  aria-label="Sign out"
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[var(--line)] bg-[var(--ink-800)] text-[var(--paper-dim)] transition-colors hover:border-[var(--line-strong)] hover:text-[var(--paper)]"
                  onClick={() => void auth.signOut()}
                  title="Sign out"
                  type="button"
                >
                  <LogOut aria-hidden="true" size={15} />
                </button>
              ) : null}
            </div>
          </div>
        </header>

        {children}
      </div>

      {mobileNavigationOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="Close navigation"
            className="absolute inset-0 bg-[var(--overlay)]"
            onClick={() => setMobileNavigationOpen(false)}
            type="button"
          />
          <aside
            aria-labelledby="mobile-navigation-title"
            aria-modal="true"
            className="mobile-nav-surface absolute inset-y-0 left-0 flex w-[min(86vw,320px)] flex-col border-r border-[var(--nav-line)] bg-[var(--nav-900)] px-4 py-5 shadow-[var(--shadow-drawer)]"
            id="mobile-navigation"
            ref={mobileNavigationRef}
            role="dialog"
          >
            <div className="flex items-center justify-between gap-4">
              <div id="mobile-navigation-title">
                <Brand dark />
              </div>
              <button
                aria-label="Close navigation"
                className="grid h-9 w-9 place-items-center rounded-md border border-[var(--nav-line)] transition-colors hover:bg-[var(--nav-800)]"
                onClick={() => setMobileNavigationOpen(false)}
                ref={mobileCloseRef}
                type="button"
              >
                <X aria-hidden="true" size={18} />
              </button>
            </div>

            <div className="mt-7 border-y border-[var(--nav-line)] py-4">
              {runPicker("active-run-mobile", true)}
            </div>

            <div className="mt-5 overflow-y-auto pb-4">{navigation(true)}</div>

            {auth.enabled ? (
              <div className="mt-auto border-t border-[var(--nav-line)] pt-4">
                <p className="truncate text-xs font-medium text-[var(--nav-text)]">{auth.displayName}</p>
                <button
                  className="mt-3 flex min-h-10 w-full items-center gap-2 rounded-md border border-[var(--nav-line)] px-3 text-xs font-medium text-[var(--nav-muted)] transition-colors hover:bg-[var(--nav-800)] hover:text-[var(--nav-text)]"
                  onClick={() => void auth.signOut()}
                  type="button"
                >
                  <LogOut aria-hidden="true" size={15} />
                  Sign out
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
