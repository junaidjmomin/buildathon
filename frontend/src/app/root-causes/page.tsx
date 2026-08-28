"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitBranch, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { resolveActiveRun, useActiveRunId, useActiveRunOverride } from "@/lib/active-run";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function RootCausesPage() {
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun?.id],
    queryFn: () => api.rootCauses(activeRun?.id ?? ""),
    enabled: Boolean(activeRun),
  });

  if (runs.isPending || (Boolean(activeRun) && roots.isPending)) {
    return (
      <AppShell>
        <div className="grid min-h-[calc(100vh-64px)] place-items-center">
          <LoaderCircle className="animate-spin text-[#1e6b51]" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
        <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">
          <GitBranch size={14} /> Deterministic clustering
        </p>
        <h1 className="text-3xl font-semibold tracking-[-0.035em]">Root causes</h1>
        <p className="mt-2 text-sm text-[#66716b]">
          {activeRun ? activeRun.name : "No completed control run is selected."}
        </p>

        <section className="mt-7 grid gap-4 md:grid-cols-2">
          {roots.data?.map((root) => (
            <Link
              key={root.id}
              href={`/root-causes/${root.id}`}
              className="panel rounded-2xl p-5 transition hover:-translate-y-0.5 hover:border-[#bfd6c8]"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[10px] text-[#758079]">{root.id}</p>
                  <h2 className="mt-1 text-base font-semibold">{root.title}</h2>
                  <p className="mt-2 text-xs text-[#66716b]">
                    {root.affected_count} affected · {root.primary_violation_count} primary · {root.downstream_effect_count} downstream
                  </p>
                </div>
                <ArrowRight size={16} className="mt-1 shrink-0 text-[#1e6b51]" />
              </div>
              <p className="mt-5 border-t border-[#e2e5df] pt-4 text-xl font-semibold text-[#a9431f]">
                {formatMoney(root.verified_impact)}
              </p>
            </Link>
          ))}
        </section>

        {runs.isError ? (
          <div className="panel mt-7 rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            Runs could not be loaded.{" "}
            <button type="button" onClick={() => runs.refetch()} className="font-semibold underline">
              Retry
            </button>
          </div>
        ) : !activeRun ? (
          <div className="panel mt-7 rounded-2xl p-8 text-sm text-[#66716b]">
            Upload source files or connect Razorpay to create a run.
          </div>
        ) : roots.isError ? (
          <div className="panel mt-7 rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            Root causes could not be loaded.{" "}
            <button type="button" onClick={() => roots.refetch()} className="font-semibold underline">
              Retry
            </button>
          </div>
        ) : roots.data?.length === 0 ? (
          <div className="panel mt-7 rounded-2xl p-8 text-sm text-[#66716b]">
            No deterministic violation clusters were found for this run.
          </div>
        ) : null}
      </main>
    </AppShell>
  );
}
