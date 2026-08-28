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
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

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
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const items = [
    { label: "Overview", icon: LayoutDashboard, href: "/" },
    {
      label: "Controls",
      icon: ShieldCheck,
      href: "/controls",
    },
    { label: "Exceptions", icon: TriangleAlert, href: "/exceptions" },
    { label: "Root causes", icon: GitBranch, href: "/root-causes" },
    { label: "Agreements", icon: FileCheck2, href: "/agreements" },
    { label: "Data sources", icon: Boxes, href: "/data" },
  ];
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      {isNavigating ? <div aria-label="Loading page" className="fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden bg-[#cfe1d6]"><div className="h-full w-2/3 animate-pulse bg-[#1e6b51]" /></div> : null}
      <aside className="hidden min-h-screen bg-[#112a2b] px-4 py-5 text-white lg:flex lg:flex-col">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-[#dff2e8] text-[#174b3b]">
            <Gauge size={20} strokeWidth={2.4} />
          </span>
          <span>
            <span className="block text-[21px] font-semibold leading-5 tracking-[-0.04em]">sl3dge</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-white/45">Control engine</span>
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
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] transition ${
                active ? "bg-white/10 font-medium text-white" : "text-white/58 hover:bg-white/5 hover:text-white"
              }`}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={16} /> {label}
            </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.055] p-3.5">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium">
            <Sparkles size={14} className="text-[#95d6b8]" /> Verification principle
          </div>
          <p className="text-[11px] leading-5 text-white/50">AI proposes. Controls calculate. Evidence decides.</p>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-[#dfe2db] bg-[#f3f4ef]/90 px-5 backdrop-blur-xl md:px-8">
          <div className="flex items-center gap-2 text-xs text-[#66716b]">
            <ShieldCheck size={15} className="text-[#1e6b51]" />
            <span className="font-medium text-[#17211d]">Financial controls</span>
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
                className="max-w-56 bg-transparent font-medium text-[#52615a] outline-none"
              >
                <option value="">Select a run</option>
                {runs.data.map((run) => (
                  <option key={run.id} value={run.id}>
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
              <span className="hidden max-w-44 truncate text-[11px] font-medium text-[#52615a] sm:inline">
                {auth.displayName}
              </span>
            ) : null}
            <div className="flex items-center gap-2 rounded-full border border-[#cdd7cf] bg-white px-3 py-1.5 text-[11px] font-medium text-[#1e6b51]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2a9b6a]" /> Verification-first
            </div>
            {auth.enabled ? (
              <button
                aria-label="Sign out"
                className="grid h-8 w-8 place-items-center rounded-full border border-[#cdd7cf] bg-white text-[#52615a] hover:text-[#17211d]"
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
          className="sticky top-16 z-10 flex gap-1 overflow-x-auto border-b border-[#dfe2db] bg-[#f8f9f5] px-3 py-2 lg:hidden"
        >
          {items.map(({ label, icon: Icon, href }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={label}
                href={href}
                onClick={() => { if (href !== pathname) setPendingHref(href); }}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${
                  active ? "bg-[#dfeee6] text-[#174b3b]" : "text-[#52615a]"
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
