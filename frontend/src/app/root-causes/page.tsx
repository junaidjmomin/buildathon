"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleDollarSign, GitBranch, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState, ErrorState, MoneyText, PageHeader, PageSkeleton } from "@/components/ui/primitives";
import { resolveActiveRun, useActiveRunId, useActiveRunOverride } from "@/lib/active-run";
import { api } from "@/lib/api";
import { compareDecimals, formatMoney } from "@/lib/format";

type RootSort = "impact" | "affected" | "name";

export default function RootCausesPage() {
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<RootSort>("impact");
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun?.id],
    queryFn: () => api.rootCauses(activeRun?.id ?? ""),
    enabled: Boolean(activeRun),
    placeholderData: (previous) => previous,
  });

  const sortedRoots = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const filtered = (roots.data ?? []).filter((root) =>
      `${root.title} ${root.category} ${root.id}`.toLocaleLowerCase().includes(normalizedQuery),
    );
    return filtered.sort((left, right) => {
      if (sort === "affected") return right.affected_count - left.affected_count;
      if (sort === "name") return left.title.localeCompare(right.title);
      return compareDecimals(right.verified_impact, left.verified_impact);
    });
  }, [query, roots.data, sort]);

  const topRoot = useMemo(
    () => (roots.data ?? []).slice().sort((left, right) => compareDecimals(right.verified_impact, left.verified_impact))[0],
    [roots.data],
  );
  const affectedEvents = (roots.data ?? []).reduce((total, root) => total + root.affected_count, 0);

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <PageHeader
          eyebrow={<><GitBranch size={14} /> Investigation queue</>}
          title="Root causes"
          subtitle={activeRun ? `Prioritized clusters for ${activeRun.name}` : "Select or create a completed control run to begin."}
        />
        {activeRun ? (
          <Link
            href="/exceptions"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] transition-colors hover:bg-[var(--ink-700)]"
          >
            Review exceptions <ArrowRight size={14} />
          </Link>
        ) : null}
      </div>

      {runs.isPending ? (
        <PageSkeleton cards={0} rows={5} />
      ) : runs.isError ? (
        <ErrorState what="Runs" onRetry={() => void runs.refetch()} />
      ) : !activeRun ? (
        <EmptyState
          title="No completed run selected"
          body="Connect Razorpay or upload source files to create a control run, then return here to investigate grouped failures."
          action={<Link href="/data" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--evergreen)]">Open data sources <ArrowRight size={14} /></Link>}
        />
      ) : roots.isPending ? (
        <PageSkeleton cards={0} rows={5} />
      ) : roots.isError ? (
        <ErrorState what="Root causes" onRetry={() => void roots.refetch()} />
      ) : roots.data?.length === 0 ? (
        <EmptyState
          title="No violation clusters found"
          body="This run has no deterministic failures grouped into a root cause. Review the run outcomes or investigate any unresolved exceptions."
          action={<Link href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--evergreen)]">Return to overview <ArrowRight size={14} /></Link>}
        />
      ) : (
        <>
          <section className="mb-5 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] lg:grid-cols-[1.35fr_0.65fr]" aria-label="Root cause summary">
            <div className="border-b border-[var(--line)] p-5 lg:border-b-0 lg:border-r md:p-6">
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[rgba(196,69,54,0.1)] text-[var(--crimson)]">
                  <CircleDollarSign size={17} />
                </span>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--paper-faint)]">Largest verified exposure</p>
                  <MoneyText amount={formatMoney(topRoot.verified_impact)} tone="violation" className="mt-1 block text-2xl tracking-[-0.035em]" />
                  <Link href={`/root-causes/${topRoot.id}`} className="mt-2 inline-flex max-w-full items-center gap-1.5 text-sm font-semibold text-[var(--paper)] hover:text-[var(--evergreen)]">
                    <span className="truncate">{topRoot.title}</span> <ArrowRight size={13} className="shrink-0" />
                  </Link>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 divide-x divide-[var(--line)]">
              <SummaryValue label="Clusters" value={(roots.data?.length ?? 0).toLocaleString("en-IN")} />
              <SummaryValue label="Affected records" value={affectedEvents.toLocaleString("en-IN")} />
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
            <div className="flex flex-col gap-3 border-b border-[var(--line)] bg-[var(--ink-700)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-[var(--paper)]">Prioritized investigations</h2>
                <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Open a cluster to review the evidence, affected payments and causal chain.</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <label className="relative block">
                  <span className="sr-only">Search root causes</span>
                  <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--paper-faint)]" />
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search clusters"
                    className="h-9 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] pl-9 pr-3 text-xs text-[var(--paper)] placeholder:text-[var(--paper-faint)] sm:w-48"
                  />
                </label>
                <label>
                  <span className="sr-only">Sort root causes</span>
                  <select
                    value={sort}
                    onChange={(event) => setSort(event.target.value as RootSort)}
                    className="h-9 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3 text-xs font-medium text-[var(--paper)] sm:w-auto"
                  >
                    <option value="impact">Highest impact</option>
                    <option value="affected">Most affected</option>
                    <option value="name">Name</option>
                  </select>
                </label>
              </div>
            </div>

            {sortedRoots.length === 0 ? (
              <div className="px-5 py-12 text-center">
                <p className="text-sm font-semibold text-[var(--paper)]">No clusters match your search</p>
                <button type="button" onClick={() => setQuery("")} className="mt-2 text-xs font-semibold text-[var(--evergreen)] hover:underline">Clear search</button>
              </div>
            ) : (
              <div className="divide-y divide-[var(--line)]">
                <div className="hidden grid-cols-[minmax(0,1fr)_130px_190px_130px_24px] gap-4 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)] md:grid">
                  <span>Root cause</span><span>Verification</span><span>Scope</span><span className="text-right">Verified impact</span><span />
                </div>
                {sortedRoots.map((root) => (
                  <Link
                    key={root.id}
                    href={`/root-causes/${root.id}`}
                    className="group grid gap-3 px-5 py-4 transition-colors hover:bg-[var(--ink-700)] md:grid-cols-[minmax(0,1fr)_130px_190px_130px_24px] md:items-center md:gap-4"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[var(--paper)]">{root.title}</p>
                      <p className="mt-1 truncate font-mono text-[10px] text-[var(--paper-faint)]">{root.id} · {root.category}</p>
                    </div>
                    <span className="w-fit rounded-full border border-[rgba(18,112,99,0.22)] bg-[rgba(18,112,99,0.08)] px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.08em] text-[var(--evergreen)]">
                      {root.verification_status.replaceAll("_", " ")}
                    </span>
                    <p className="text-xs text-[var(--paper-dim)]">
                      <span className="font-semibold text-[var(--paper)]">{root.affected_count.toLocaleString("en-IN")}</span> affected · {root.primary_violation_count.toLocaleString("en-IN")} primary · {root.downstream_effect_count.toLocaleString("en-IN")} downstream
                    </p>
                    <MoneyText amount={formatMoney(root.verified_impact)} tone="violation" className="text-sm md:text-right" />
                    <ArrowRight size={15} className="hidden text-[var(--paper-faint)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--evergreen)] md:block" />
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function SummaryValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col justify-center p-5">
      <p className="number-tabular font-mono text-xl font-semibold tracking-[-0.03em] text-[var(--paper)]">{value}</p>
      <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}
