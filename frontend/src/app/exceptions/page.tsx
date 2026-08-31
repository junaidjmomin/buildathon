"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, CircleAlert, Clock3, FileCheck2, LoaderCircle, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge, EmptyState, ErrorState, MoneyText, PageHeader, PageSkeleton } from "@/components/ui/primitives";
import { resolveActiveRun, useActiveRunId, useActiveRunOverride } from "@/lib/active-run";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ExceptionCase, ExceptionCaseStatus } from "@/types/api";

type CaseFilter = "ALL" | ExceptionCaseStatus;
const CASE_FILTERS: CaseFilter[] = ["ALL", "OPEN", "VERIFIED", "ESCALATED", "RESOLVED"];

export default function ExceptionsPage() {
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CaseFilter>("ALL");
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const activeRunId = activeRun?.id;
  const cases = useQuery({
    queryKey: ["exception-cases", activeRunId],
    queryFn: () => api.exceptionCases(activeRunId ?? ""),
    enabled: Boolean(activeRunId),
  });
  const unresolved = useQuery({
    queryKey: ["unresolved", activeRunId],
    queryFn: () => api.unresolvedMatches(activeRunId ?? ""),
    enabled: Boolean(activeRunId),
  });
  const violations = useQuery({
    queryKey: ["violations", activeRunId],
    queryFn: () => api.violations(activeRunId ?? ""),
    enabled: Boolean(activeRunId),
  });
  const transition = useMutation({
    mutationFn: ({ caseId, action, note, version }: { caseId: string; action: "verify" | "escalate" | "resolve"; note: string; version: number }) => api.transitionCase(caseId, action, note, version),
    onSuccess: (updated) => queryClient.setQueryData<ExceptionCase[]>(["exception-cases", activeRunId], (current) => current?.map((item) => item.id === updated.id ? updated : item) ?? [updated]),
  });

  const visibleCases = useMemo(
    () => (cases.data ?? []).filter((item) => statusFilter === "ALL" || item.status === statusFilter),
    [cases.data, statusFilter],
  );
  const active = visibleCases.find((item) => item.id === selectedCaseId) ?? visibleCases[0];
  const activeViolation = active
    ? violations.data?.find((item) => item.id === active.primary_violation_id)
    : undefined;
  const pendingReviewCount = (cases.data ?? []).filter((item) => item.status === "OPEN" || item.status === "VERIFIED").length;
  const escalatedCount = (cases.data ?? []).filter((item) => item.status === "ESCALATED").length;
  const resolvedCount = (cases.data ?? []).filter((item) => item.status === "RESOLVED").length;

  const act = (action: "verify" | "escalate" | "resolve") => {
    if (!active) return;
    const notes = {
      verify: "",
      escalate: "Escalated to the gateway finance owner with the complete evidence pack.",
      resolve: "Recovery acknowledged and case resolved with its evidence trail preserved.",
    };
    transition.mutate({ caseId: active.id, action, note: notes[action], version: active.version });
  };

  return (
    <main className="mx-auto max-w-[1320px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow={<><FileCheck2 size={14} /> Exception operations</>}
        title="Review and resolve exceptions"
        subtitle={activeRun ? `Evidence-backed cases for ${activeRun.name}` : "Select or create a completed run to begin review."}
      />

      {runs.isPending || (Boolean(activeRunId) && (cases.isPending || unresolved.isPending || violations.isPending)) ? (
        <PageSkeleton cards={0} rows={6} />
      ) : runs.isError ? (
        <ErrorState what="Runs" onRetry={() => void runs.refetch()} />
      ) : !activeRunId ? (
        <EmptyState
          title="No completed run selected"
          body="Connect Razorpay or upload source files before reviewing financial exceptions."
          action={<Link href="/data" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--evergreen)]">Open data sources <ArrowRight size={14} /></Link>}
        />
      ) : cases.isError || unresolved.isError || violations.isError ? (
        <ErrorState what="Exception cases" onRetry={() => { void cases.refetch(); void unresolved.refetch(); void violations.refetch(); }} />
      ) : (
        <>
          <section className="mb-5 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] sm:grid-cols-4" aria-label="Exception summary">
            <QueueMetric label="All cases" value={(cases.data?.length ?? 0).toLocaleString("en-IN")} />
            <QueueMetric label="Pending review" value={pendingReviewCount.toLocaleString("en-IN")} tone={pendingReviewCount > 0 ? "warning" : "default"} />
            <QueueMetric label="Escalated" value={escalatedCount.toLocaleString("en-IN")} />
            <QueueMetric label="Resolved" value={resolvedCount.toLocaleString("en-IN")} tone="pass" />
          </section>

          {cases.data?.length === 0 ? (
            <EmptyState
              title="No exception cases for this run"
              body="No evidence-backed violation cases need action. Unresolved records, if any, remain visible below and are not forced into a match."
              action={<Link href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--evergreen)]">Review run outcomes <ArrowRight size={14} /></Link>}
            />
          ) : (
            <section className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
              <aside className="h-fit overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] lg:sticky lg:top-24">
                <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-sm font-semibold text-[var(--paper)]">Case queue</h2>
                      <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Choose a case to inspect.</p>
                    </div>
                    <span className="number-tabular font-mono text-xs font-semibold text-[var(--paper-dim)]">{visibleCases.length}/{cases.data?.length ?? 0}</span>
                  </div>
                  <div className="mt-3 flex gap-1 overflow-x-auto pb-1" aria-label="Filter cases by status">
                    {CASE_FILTERS.map((filter) => {
                      const count = filter === "ALL" ? cases.data?.length ?? 0 : (cases.data ?? []).filter((item) => item.status === filter).length;
                      return (
                        <button
                          key={filter}
                          type="button"
                          aria-pressed={statusFilter === filter}
                          onClick={() => setStatusFilter(filter)}
                          className={`shrink-0 rounded-md px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.06em] transition-colors ${statusFilter === filter ? "bg-[var(--evergreen)] text-[var(--ink-800)]" : "text-[var(--paper-dim)] hover:bg-[var(--ink-600)]"}`}
                        >
                          {filter === "ALL" ? "All" : filter} · {count}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {visibleCases.length === 0 ? (
                  <div className="px-4 py-10 text-center">
                    <p className="text-xs font-semibold text-[var(--paper)]">No cases with this status</p>
                    <button type="button" onClick={() => setStatusFilter("ALL")} className="mt-2 text-xs font-semibold text-[var(--evergreen)] hover:underline">Show all cases</button>
                  </div>
                ) : (
                  <div className="max-h-[560px] divide-y divide-[var(--line)] overflow-y-auto">
                    {visibleCases.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        aria-pressed={active?.id === item.id}
                        onClick={() => { setSelectedCaseId(item.id); transition.reset(); }}
                        className={`w-full px-4 py-3.5 text-left transition-colors ${active?.id === item.id ? "bg-[var(--ink-700)] shadow-[inset_3px_0_0_var(--evergreen)]" : "hover:bg-[var(--ink-700)]"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="line-clamp-2 text-xs font-semibold leading-5 text-[var(--paper)]">{item.title}</p>
                          <CaseBadge status={item.status} compact />
                        </div>
                        <div className="mt-2 flex items-end justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate font-mono text-[9px] text-[var(--paper-faint)]">{item.id}</p>
                            <p className="mt-0.5 truncate font-mono text-[10px] text-[var(--paper-dim)]">{item.payment_id}</p>
                          </div>
                          <MoneyText amount={formatMoney(item.verified_impact)} tone="violation" className="shrink-0 text-xs" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </aside>

              {active ? (
                <div className="min-w-0 space-y-5">
                  <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
                    <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-4">
                      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <CaseBadge status={active.status} />
                            <span className="font-mono text-[10px] text-[var(--paper-faint)]">{active.id}</span>
                          </div>
                          <h2 className="mt-2 text-xl font-semibold tracking-[-0.025em] text-[var(--paper)]">{active.title}</h2>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                            {activeViolation?.target_type === "PAYMENT" ? (
                              <Link href={`/runs/${activeRunId}/payments/${active.payment_id}`} className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-[var(--evergreen)] hover:underline">
                                {active.payment_id} · open payment proof <ArrowRight size={12} />
                              </Link>
                            ) : (
                              <span className="font-mono text-xs text-[var(--paper-dim)]">{active.payment_id}</span>
                            )}
                            {active.root_cause_id ? (
                              <Link href={`/root-causes/${active.root_cause_id}`} className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--evergreen)] hover:underline">
                                Open root cause <ArrowRight size={12} />
                              </Link>
                            ) : null}
                          </div>
                        </div>
                        <div className="shrink-0 sm:text-right">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">Verified impact</p>
                          <MoneyText amount={formatMoney(active.verified_impact)} tone="violation" className="mt-1 block text-2xl tracking-[-0.035em]" />
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col justify-between gap-4 px-5 py-4 sm:flex-row sm:items-center">
                      <div>
                        <p className="text-xs font-semibold text-[var(--paper)]">Next case action</p>
                        <p className="mt-1 text-[11px] text-[var(--paper-dim)]">Transitions are recorded with the current evidence version.</p>
                      </div>
                      <CaseActions status={active.status} pending={transition.isPending} act={act} />
                    </div>
                    {transition.isSuccess ? <p role="status" className="border-t border-[var(--line)] px-5 py-3 text-xs font-semibold text-[var(--evergreen)]">Case updated. The new status is in the audit trail.</p> : null}
                    {transition.isError ? <p role="alert" className="border-t border-[var(--line)] px-5 py-3 text-xs text-[var(--crimson)]">Case update failed: {transition.error.message}</p> : null}
                  </section>

                  <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
                    <div className="flex items-center justify-between gap-4 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5">
                      <div>
                        <h2 className="text-sm font-semibold text-[var(--paper)]">Evidence pack</h2>
                        <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Inputs used to verify this case.</p>
                      </div>
                      <span className="number-tabular font-mono text-xs font-semibold text-[var(--evergreen)]">{active.evidence.filter((item) => item.verified).length}/{active.evidence.length} verified</span>
                    </div>
                    {active.evidence.length === 0 ? (
                      <p className="px-5 py-8 text-sm text-[var(--paper-dim)]">No evidence items are attached to this case.</p>
                    ) : (
                      <div className="divide-y divide-[var(--line)]">
                        {active.evidence.map((item) => (
                          <article key={item.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[34px_minmax(0,1fr)_auto] sm:items-start">
                            <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--ink-700)] text-[var(--evergreen)]"><ShieldCheck size={15} /></span>
                            <div className="min-w-0">
                              <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-[var(--paper-faint)]">{item.kind}</p>
                              <h3 className="mt-1 text-xs font-semibold text-[var(--paper)]">{item.title}</h3>
                              <p className="mt-1 text-[11px] leading-5 text-[var(--paper-dim)]">{item.summary}</p>
                              <p className="mt-2 truncate font-mono text-[9px] text-[var(--paper-faint)]">Source · {item.source_id}</p>
                            </div>
                            <Badge status={item.verified ? "PASS" : "PENDING"} label={item.verified ? "Verified" : "Pending"} />
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
                    <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5">
                      <h2 className="text-sm font-semibold text-[var(--paper)]">Audit trail</h2>
                      <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Append-only status history.</p>
                    </div>
                    {active.audit_trail.length === 0 ? (
                      <p className="px-5 py-8 text-sm text-[var(--paper-dim)]">No reviewer actions have been recorded.</p>
                    ) : (
                      <ol className="divide-y divide-[var(--line)]">
                        {active.audit_trail.map((entry) => (
                          <li key={`${entry.to_status}-${entry.occurred_at}`} className="grid gap-2 px-5 py-3.5 sm:grid-cols-[120px_minmax(0,1fr)_auto] sm:items-start">
                            <p className="flex items-center gap-1.5 text-xs font-semibold text-[var(--paper)]"><Check size={12} className="text-[var(--evergreen)]" /> {entry.to_status}</p>
                            <p className="text-[11px] leading-5 text-[var(--paper-dim)]">{entry.note || "Status updated."}</p>
                            <p className="font-mono text-[9px] text-[var(--paper-faint)] sm:text-right">{entry.actor}<span className="block">{new Date(entry.occurred_at).toLocaleString("en-IN")}</span></p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                </div>
              ) : null}
            </section>
          )}

          <UnresolvedQueue activeRunId={activeRunId} seeded={activeRun?.source_type === "DEMO"} items={unresolved.data ?? []} />
        </>
      )}
    </main>
  );
}

function QueueMetric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "pass" | "warning" }) {
  const toneClass = tone === "pass" ? "text-[var(--evergreen)]" : tone === "warning" ? "text-[var(--amber)]" : "text-[var(--paper)]";
  return (
    <div className="border-b border-[var(--line)] px-5 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <p className={`number-tabular font-mono text-xl font-semibold tracking-[-0.03em] ${toneClass}`}>{value}</p>
      <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}

function UnresolvedQueue({ activeRunId, seeded, items }: { activeRunId: string; seeded: boolean; items: Awaited<ReturnType<typeof api.unresolvedMatches>> }) {
  return (
    <section className="mt-5 overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
      <div className="flex flex-col justify-between gap-3 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-sm font-semibold text-[var(--paper)]">Unresolved matches</h2>
          <p className="mt-0.5 text-xs text-[var(--paper-dim)]">Records held back because the available evidence cannot support a unique match.</p>
        </div>
        <Badge status={items.length > 0 ? "UNRESOLVED" : "PASS"} label={`${items.length} ${items.length === 1 ? "record" : "records"}`} />
      </div>
      {items.length === 0 ? (
        <div className="flex items-center gap-2 px-5 py-5 text-xs text-[var(--paper-dim)]"><Check size={14} className="text-[var(--evergreen)]" /> No ambiguous records remain in this run.</div>
      ) : (
        <div className="divide-y divide-[var(--line)]">
          {items.map((item) => (
            <article key={item.id} className="grid gap-3 px-5 py-4 transition-colors hover:bg-[var(--ink-700)] lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_auto] lg:items-center">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <CircleAlert size={14} className="shrink-0 text-[var(--amber)]" />
                  {seeded ? <Link href={`/runs/${activeRunId}/payments/${item.payment_id}`} className="truncate font-mono text-xs font-semibold text-[var(--evergreen)] hover:underline">{item.payment_id}</Link> : <span className="truncate font-mono text-xs font-semibold text-[var(--paper)]">{item.payment_id}</span>}
                </div>
                <p className="mt-1 truncate font-mono text-[9px] text-[var(--paper-faint)]">{item.id} · settlement {item.settlement_id}</p>
              </div>
              <div>
                <p className="text-xs text-[var(--paper)]">{item.missing_evidence}</p>
                <p className="mt-1 text-[10px] leading-4 text-[var(--paper-dim)]">{item.safe_conclusion}</p>
                {item.candidate_bank_references.length > 0 ? <p className="mt-1.5 truncate font-mono text-[9px] text-[var(--paper-faint)]">Candidates · {item.candidate_bank_references.join(" · ")}</p> : null}
              </div>
              <MoneyText amount={formatMoney(item.amount)} tone="warning" className="text-sm lg:text-right" />
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function CaseActions({ status, pending, act }: { status: ExceptionCaseStatus; pending: boolean; act: (action: "verify" | "escalate" | "resolve") => void }) {
  if (status === "RESOLVED") return <p className="flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)]"><Check size={14} /> Resolved</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {status === "OPEN" ? (
        <button onClick={() => act("verify")} disabled={pending} className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] disabled:cursor-wait disabled:opacity-60">
          {pending ? <LoaderCircle size={13} className="animate-spin" /> : <ShieldCheck size={13} />} Verify evidence
        </button>
      ) : null}
      {status === "VERIFIED" ? (
        <>
          <button onClick={() => act("escalate")} disabled={pending} className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] disabled:opacity-60"><Send size={13} /> Escalate</button>
          <button onClick={() => act("resolve")} disabled={pending} className="rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] disabled:opacity-60">Resolve</button>
        </>
      ) : null}
      {status === "ESCALATED" ? <button onClick={() => act("resolve")} disabled={pending} className="rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] disabled:opacity-60">Resolve with evidence</button> : null}
    </div>
  );
}

function CaseBadge({ status, compact = false }: { status: ExceptionCaseStatus; compact?: boolean }) {
  const statusMap: Record<ExceptionCaseStatus, { badge: "PASS" | "PENDING" | "INFO"; icon: typeof Check }> = {
    OPEN: { badge: "PENDING", icon: Clock3 },
    VERIFIED: { badge: "PASS", icon: ShieldCheck },
    ESCALATED: { badge: "INFO", icon: Send },
    RESOLVED: { badge: "PASS", icon: Check },
  };
  const { badge, icon: Icon } = statusMap[status];
  if (compact) return <span title={status} className="text-[var(--paper-faint)]"><Icon size={13} aria-label={status} /></span>;
  return <Badge status={badge} label={status} />;
}
