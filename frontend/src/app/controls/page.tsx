"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, ChevronDown, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge, EmptyState, ErrorState, PageHeader, PageSkeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function ControlsPage() {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });

  const statuses = useMemo(
    () => Array.from(new Set((controls.data ?? []).map((control) => control.status))).sort(),
    [controls.data],
  );
  const visibleControls = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return (controls.data ?? []).filter((control) => {
      const matchesStatus = statusFilter === "ALL" || control.status === statusFilter;
      const searchable = [control.name, control.id, control.logical_control_key, control.scope, control.source, control.source_clause]
        .join(" ")
        .toLocaleLowerCase();
      return matchesStatus && searchable.includes(normalizedQuery);
    });
  }, [controls.data, query, statusFilter]);

  const approvedCount = (controls.data ?? []).filter((control) => control.status === "APPROVED").length;
  const logicalControlCount = new Set((controls.data ?? []).map((control) => control.logical_control_key)).size;

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <PageHeader
          eyebrow={<><ShieldCheck size={14} /> Control governance</>}
          title="Control registry"
          subtitle="The approved rules used to calculate expected financial behavior, with source clauses and version history attached."
        />
        <Link
          href="/agreements"
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] transition-colors hover:bg-[var(--ink-700)]"
        >
          <BookOpenText size={14} /> Review agreements
        </Link>
      </div>

      {controls.isPending ? (
        <PageSkeleton cards={0} rows={6} />
      ) : controls.isError ? (
        <ErrorState what="Controls" onRetry={() => void controls.refetch()} />
      ) : controls.data?.length === 0 ? (
        <EmptyState
          title="No controls in the registry"
          body="Review an agreement, verify its proposed rules and approve a version before running financial checks."
          action={<Link href="/agreements" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--evergreen)]">Open agreements <ArrowRight size={14} /></Link>}
        />
      ) : (
        <>
          <section className="mb-5 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] sm:grid-cols-3" aria-label="Control registry summary">
            <RegistryMetric label="Registered versions" value={(controls.data?.length ?? 0).toLocaleString("en-IN")} />
            <RegistryMetric label="Approved" value={approvedCount.toLocaleString("en-IN")} />
            <RegistryMetric label="Logical controls" value={logicalControlCount.toLocaleString("en-IN")} />
          </section>

          <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
            <div className="flex flex-col gap-3 border-b border-[var(--line)] bg-[var(--ink-700)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-[var(--paper)]">Rules in force</h2>
                <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Search by rule, source, scope or identifier.</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <label className="relative block">
                  <span className="sr-only">Search controls</span>
                  <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--paper-faint)]" />
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search controls"
                    className="h-9 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] pl-9 pr-3 text-xs text-[var(--paper)] placeholder:text-[var(--paper-faint)] sm:w-52"
                  />
                </label>
                <label>
                  <span className="sr-only">Filter controls by status</span>
                  <select
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                    className="h-9 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3 text-xs font-medium text-[var(--paper)] sm:w-auto"
                  >
                    <option value="ALL">All statuses</option>
                    {statuses.map((status) => <option value={status} key={status}>{status.replaceAll("_", " ")}</option>)}
                  </select>
                </label>
              </div>
            </div>

            {visibleControls.length === 0 ? (
              <div className="px-5 py-12 text-center">
                <p className="text-sm font-semibold text-[var(--paper)]">No controls match these filters</p>
                <button
                  type="button"
                  onClick={() => { setQuery(""); setStatusFilter("ALL"); }}
                  className="mt-2 text-xs font-semibold text-[var(--evergreen)] hover:underline"
                >
                  Clear filters
                </button>
              </div>
            ) : (
              <div className="divide-y divide-[var(--line)]">
                <div className="hidden grid-cols-[minmax(0,1.25fr)_minmax(180px,0.8fr)_150px_100px_24px] gap-4 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)] lg:grid">
                  <span>Control</span><span>Scope &amp; source</span><span>Effective</span><span>Status</span><span />
                </div>
                {visibleControls.map((control) => (
                  <article key={control.id} className="group px-5 py-4 transition-colors hover:bg-[var(--ink-700)]">
                    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(180px,0.8fr)_150px_100px_24px] lg:items-center lg:gap-4">
                      <div className="min-w-0">
                        <Link href={`/controls/${control.logical_control_key}`} className="inline-flex max-w-full items-center gap-1.5 text-sm font-semibold text-[var(--paper)] hover:text-[var(--evergreen)]">
                          <span className="truncate">{control.name}</span>
                        </Link>
                        <p className="mt-1 truncate font-mono text-[10px] text-[var(--paper-faint)]">{control.logical_control_key} · v{control.version}</p>
                      </div>
                      <div className="min-w-0 text-xs">
                        <p className="truncate font-medium text-[var(--paper)]">{control.scope}</p>
                        <p className="mt-1 truncate text-[var(--paper-dim)]" title={`${control.source} · ${control.source_clause}`}>{control.source} · {control.source_clause}</p>
                      </div>
                      <p className="text-xs text-[var(--paper-dim)]">
                        {formatControlDate(control.effective_from)}
                        {control.effective_to ? <span className="block text-[10px] text-[var(--paper-faint)]">to {formatControlDate(control.effective_to)}</span> : <span className="block text-[10px] text-[var(--evergreen)]">Current version</span>}
                      </p>
                      <Badge status={control.status === "APPROVED" ? "PASS" : "DRAFT"} label={control.status} />
                      <Link href={`/controls/${control.logical_control_key}`} aria-label={`Open ${control.name}`} className="hidden text-[var(--paper-faint)] group-hover:text-[var(--evergreen)] lg:block">
                        <ArrowRight size={15} />
                      </Link>
                    </div>

                    <details className="mt-3 border-t border-[var(--line)] pt-3">
                      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11px] font-semibold text-[var(--paper-dim)] hover:text-[var(--paper)] [&::-webkit-details-marker]:hidden">
                        <ChevronDown size={13} /> Inspect rule definition
                      </summary>
                      <div className="mt-3 grid gap-4 rounded-lg bg-[var(--ink-700)] p-4 lg:grid-cols-[1fr_0.8fr]">
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">Expected behavior</p>
                          <p className="mt-1.5 text-xs leading-5 text-[var(--paper)]">{control.expected}</p>
                          {control.conditions.length > 0 ? (
                            <div className="mt-4">
                              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">Conditions</p>
                              <ul className="mt-1.5 space-y-1 text-xs leading-5 text-[var(--paper-dim)]">
                                {control.conditions.map((condition) => <li key={condition}>• {condition}</li>)}
                              </ul>
                            </div>
                          ) : null}
                          <Link href={`/agreements/${control.agreement_id}`} className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--evergreen)] hover:underline">
                            Open source agreement <ArrowRight size={13} />
                          </Link>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">Parameters</p>
                          <pre className="number-tabular mt-1.5 overflow-x-auto rounded-lg border border-[var(--line)] bg-[var(--ink-800)] p-3 font-mono text-[10px] leading-5 text-[var(--paper-dim)]">
                            {JSON.stringify(control.parameters, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </details>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function RegistryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-[var(--line)] px-5 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <p className="number-tabular font-mono text-xl font-semibold tracking-[-0.03em] text-[var(--paper)]">{value}</p>
      <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}

function formatControlDate(value: string): string {
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
