"use client";

import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import Link from "next/link";

import { ErrorState, MoneyText, PageHeader, PageSkeleton } from "@/components/ui/primitives";
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
    placeholderData: (previous) => previous,
  });

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow={<><GitBranch size={14} /> Deterministic clustering</>}
        title="Root causes"
        subtitle={activeRun ? activeRun.name : "No completed control run is selected."}
      />

      {runs.isError ? (
        <ErrorState what="Runs" onRetry={() => runs.refetch()} />
      ) : roots.isError ? (
        <ErrorState what="Root causes" onRetry={() => roots.refetch()} />
      ) : !activeRun ? (
        <div className="panel rounded-2xl p-8 text-sm text-[var(--paper-dim)]">
          Upload source files or connect Razorpay to create a run.
        </div>
      ) : roots.isPending ? (
        <PageSkeleton cards={0} rows={4} />
      ) : roots.data?.length === 0 ? (
        <div className="panel rounded-2xl p-8 text-sm text-[var(--paper-dim)]">
          No deterministic violation clusters were found for this run.
        </div>
      ) : (
        <section className="grid gap-4 md:grid-cols-2">
          {roots.data?.map((root) => (
            <Link
              key={root.id}
              href={`/root-causes/${root.id}`}
              className="panel group rounded-2xl p-5 transition duration-150 hover:-translate-y-0.5 hover:border-[var(--line-strong)]"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[10px] text-[var(--paper-faint)]">{root.id}</p>
                  <h2 className="mt-1 text-base font-semibold text-[var(--paper)]">{root.title}</h2>
                  <p className="mt-2 text-xs text-[var(--paper-dim)]">
                    {root.affected_count} affected · {root.primary_violation_count} primary · {root.downstream_effect_count} downstream
                  </p>
                </div>
                <span aria-hidden="true" className="mt-1 text-[var(--evergreen)] transition-transform duration-150 group-hover:translate-x-0.5">→</span>
              </div>
              <p className="mt-5 border-t border-[var(--line)] pt-4 text-xl">
                <MoneyText amount={formatMoney(root.verified_impact)} tone="violation" />
              </p>
            </Link>
          ))}
        </section>
      )}
    </main>
  );
}
