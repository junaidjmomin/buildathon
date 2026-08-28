"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, CircleAlert, Clock3, FileCheck2, LoaderCircle, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, EmptyState, ErrorState, MoneyText, PageHeader } from "@/components/ui/primitives";
import { resolveActiveRun, useActiveRunId, useActiveRunOverride } from "@/lib/active-run";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ExceptionCase, ExceptionCaseStatus } from "@/types/api";

export default function ExceptionsPage() {
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const activeRun = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const activeRunId = activeRun?.id;
  const cases = useQuery({ queryKey: ["exception-cases", activeRunId], queryFn: () => api.exceptionCases(activeRunId ?? ""), enabled: Boolean(activeRunId) });
  const unresolved = useQuery({ queryKey: ["unresolved", activeRunId], queryFn: () => api.unresolvedMatches(activeRunId ?? ""), enabled: Boolean(activeRunId) });
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  useEffect(() => {
    if (cases.data?.length && !cases.data.some((item) => item.id === selectedCaseId)) {
      setSelectedCaseId(cases.data[0].id);
    }
  }, [cases.data, selectedCaseId]);
  const transition = useMutation({
    mutationFn: ({ caseId, action, note, version }: { caseId: string; action: "verify" | "escalate" | "resolve"; note: string; version: number }) => api.transitionCase(caseId, action, note, version),
    onSuccess: (updated) => queryClient.setQueryData<ExceptionCase[]>(["exception-cases", activeRunId], (current) => current?.map((item) => item.id === updated.id ? updated : item) ?? [updated]),
  });

  if (runs.isPending || (Boolean(activeRunId) && (cases.isPending || unresolved.isPending))) return <div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[var(--evergreen)]" /></div>;
  if (!activeRunId) return <main className="p-8 text-[var(--paper-dim)]">No completed tenant run is available. Sync Razorpay from Data sources first.</main>;
  if (cases.isError || unresolved.isError) return <main className="mx-auto max-w-4xl p-8"><ErrorState what="Exception cases" onRetry={() => { void cases.refetch(); void unresolved.refetch(); }} /></main>;
  const active = cases.data?.find((item) => item.id === selectedCaseId) ?? cases.data?.[0];
  if (!active) return <main className="mx-auto max-w-4xl p-8"><EmptyState title="No exception cases for this run" body="The run may have no violations, or case generation has not produced an evidence-backed case yet. Review its outcomes on Overview." /><UnresolvedQueue activeRunId={activeRunId} seeded={activeRun?.source_type === "DEMO"} items={unresolved.data ?? []} /></main>;

  const act = (action: "verify" | "escalate" | "resolve") => {
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
        eyebrow={
          <>
            <FileCheck2 size={14} /> Evidence-backed exceptions
          </>
        }
        title="Verification becomes an accountable case"
        subtitle="A case cannot skip deterministic verification. Every transition remains in the audit trail."
      />

      {cases.data && cases.data.length > 1 ? (
        <section className="panel mb-6 overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
            <div><h2 className="text-sm font-semibold text-[var(--paper)]">Exception inbox</h2><p className="mt-1 text-xs text-[var(--paper-faint)]">Select a case to inspect its evidence and workflow.</p></div>
            <span className="number-tabular rounded-full border border-[var(--line-strong)] px-2.5 py-1 font-mono text-[10px] text-[var(--paper-dim)]">{cases.data.length} cases</span>
          </div>
          <div className="grid max-h-44 gap-2 overflow-y-auto p-3 sm:grid-cols-2 lg:grid-cols-3">
            {cases.data.map((item) => (
              <button key={item.id} type="button" onClick={() => setSelectedCaseId(item.id)} className={`rounded-xl border px-3 py-3 text-left transition-colors ${item.id === active.id ? "border-[var(--evergreen)] bg-[rgba(47,189,127,0.1)]" : "border-[var(--line)] bg-[var(--ink-700)] hover:border-[var(--line-strong)]"}`}>
                <span className="block truncate text-xs font-semibold text-[var(--paper)]">{item.title}</span>
                <span className="mt-1 block font-mono text-[10px] text-[var(--paper-faint)]">{item.id} · {item.status}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className="mb-6 grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
        <div className="space-y-4">
          <div className="panel rounded-2xl p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-[10px] text-[var(--paper-faint)]">{active.id}</p>
                <h2 className="mt-1 text-base font-semibold text-[var(--paper)]">{active.title}</h2>
                {activeRun?.source_type === "DEMO" ? <Link href={`/runs/${activeRunId}/payments/${active.payment_id}`} className="mt-1 flex items-center gap-1 text-xs font-semibold text-[var(--evergreen)] transition-colors duration-150">{active.payment_id} <ArrowRight size={12} /></Link> : active.root_cause_id ? <Link href={`/root-causes/${active.root_cause_id}`} className="mt-1 flex items-center gap-1 text-xs font-semibold text-[var(--evergreen)] transition-colors duration-150">{active.payment_id} <ArrowRight size={12} /></Link> : <span className="number-tabular mt-1 block font-mono text-xs text-[var(--paper-dim)]">{active.payment_id}</span>}
              </div>
              <CaseBadge status={active.status} />
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)] p-3">
                <p className="text-[9px] uppercase tracking-[0.11em] text-[var(--crimson)]">Verified impact</p>
                <MoneyText className="mt-1 text-lg" amount={formatMoney(active.verified_impact)} tone="violation" />
              </div>
              <div className="rounded-xl border border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.14)] p-3">
                <p className="text-[9px] uppercase tracking-[0.11em] text-[var(--evergreen)]">Evidence items</p>
                <p className="number-tabular mt-1 font-mono text-lg font-semibold text-[var(--evergreen)]">{active.evidence.length}</p>
              </div>
            </div>
            <CaseActions status={active.status} pending={transition.isPending} act={act} />
            {transition.isSuccess && <p role="status" className="mt-3 text-xs font-semibold text-[var(--evergreen)]">Case updated successfully. The audit trail has been refreshed.</p>}
            {transition.isError && <p role="alert" className="mt-3 text-xs text-[var(--crimson)]">Case update failed: {transition.error.message}</p>}
          </div>

          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[var(--line)] px-5 py-4">
              <h2 className="text-sm font-semibold text-[var(--paper)]">Status audit trail</h2>
              <p className="mt-1 text-xs text-[var(--paper-faint)]">Append-only reviewer actions</p>
            </div>
            <div className="p-5">
              {active.audit_trail.map((entry, index) => (
                <div key={`${entry.to_status}-${entry.occurred_at}`} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className="grid h-7 w-7 place-items-center rounded-full bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]"><Check size={12} /></span>
                    {index < active.audit_trail.length - 1 && <span className="min-h-10 w-px flex-1 bg-[var(--line)]" />}
                  </div>
                  <div className="pb-5">
                    <p className="text-xs font-semibold text-[var(--paper)]">{entry.to_status}</p>
                    <p className="mt-1 text-[10px] leading-4 text-[var(--paper-dim)]">{entry.note}</p>
                    <p className="mt-1 font-mono text-[9px] text-[var(--paper-faint)]">{entry.actor} · {new Date(entry.occurred_at).toLocaleString("en-IN")}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold text-[var(--paper)]">Deterministic evidence pack</h2>
              <p className="mt-1 text-xs text-[var(--paper-faint)]">Proof required before VERIFIED</p>
            </div>
            <span className="number-tabular rounded-full border border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.14)] px-2.5 py-1 font-mono text-[10px] font-bold text-[var(--evergreen)]">{active.evidence.filter((item) => item.verified).length}/{active.evidence.length} VERIFIED</span>
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-2">
            {active.evidence.map((item) => (
              <div key={item.id} className="rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-4">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]"><ShieldCheck size={15} /></span>
                  <Badge status="PASS" label="VERIFIED" />
                </div>
                <p className="mt-3 text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--paper-faint)]">{item.kind}</p>
                <h3 className="mt-1 text-xs font-semibold text-[var(--paper)]">{item.title}</h3>
                <p className="mt-2 text-[11px] leading-5 text-[var(--paper-dim)]">{item.summary}</p>
                <p className="number-tabular mt-3 border-t border-[var(--line)] pt-3 font-mono text-[9px] text-[var(--paper-faint)]">{item.source_id}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <UnresolvedQueue activeRunId={activeRunId} seeded={activeRun?.source_type === "DEMO"} items={unresolved.data ?? []} />
    </main>
  );
}

function UnresolvedQueue({ activeRunId, seeded, items }: { activeRunId: string; seeded: boolean; items: Awaited<ReturnType<typeof api.unresolvedMatches>> }) {
  return (
    <section className="panel mt-6 overflow-hidden rounded-2xl">
      <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-[var(--paper)]">Honest unresolved queue</h2>
          <p className="mt-1 text-xs text-[var(--paper-faint)]">Ambiguous records are never forced into a match</p>
        </div>
        <span className="number-tabular rounded-full border border-[rgba(227,179,65,0.35)] bg-[rgba(227,179,65,0.14)] px-2.5 py-1 font-mono text-[10px] font-bold text-[var(--amber)]">{items.length} UNRESOLVED</span>
      </div>
      <div className="divide-y divide-[var(--line)]">
        {items.map((item) => (
          <div key={item.id} className="flex flex-col justify-between gap-3 px-5 py-4 transition-colors duration-150 hover:bg-[var(--ink-600)] sm:flex-row sm:items-center">
            <div>
              <div className="flex items-center gap-2">
                <CircleAlert size={14} className="text-[var(--amber)]" />
                <span className="number-tabular font-mono text-[10px] font-bold text-[var(--paper-faint)]">{item.id}</span>
                {seeded ? <Link href={`/runs/${activeRunId}/payments/${item.payment_id}`} className="number-tabular font-mono text-xs font-semibold text-[var(--sky)] transition-colors duration-150">{item.payment_id}</Link> : <span className="number-tabular font-mono text-xs font-semibold text-[var(--sky)]">{item.payment_id}</span>}
                <MoneyText className="text-xs" amount={formatMoney(item.amount)} />
              </div>
              <p className="mt-1 text-[10px] text-[var(--paper-dim)]">{item.missing_evidence} {item.safe_conclusion}</p>
            </div>
            <div className="flex gap-2">
              {item.candidate_bank_references.map((candidate) => (
                <span key={candidate} className="number-tabular rounded-md border border-[var(--line)] bg-[var(--ink-700)] px-2 py-1 font-mono text-[9px] text-[var(--paper-dim)]">{candidate}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CaseActions({ status, pending, act }: { status: ExceptionCaseStatus; pending: boolean; act: (action: "verify" | "escalate" | "resolve") => void }) {
  if (status === "RESOLVED") return <p className="mt-4 flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)]"><Check size={14} /> Case resolved; evidence and audit history retained.</p>;
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {status === "OPEN" && (
        <button onClick={() => act("verify")} disabled={pending} className="flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2 text-xs font-semibold text-[#06120c] transition-opacity duration-150 disabled:opacity-60">
          {pending ? <LoaderCircle size={13} className="animate-spin" /> : <ShieldCheck size={13} />} Verify evidence
        </button>
      )}
      {status === "VERIFIED" && (
        <>
          <button onClick={() => act("escalate")} disabled={pending} className="flex items-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-700)] px-3 py-2 text-xs font-semibold text-[var(--paper)] transition-colors duration-150 disabled:opacity-60"><Send size={13} /> Escalate</button>
          <button onClick={() => act("resolve")} disabled={pending} className="rounded-lg border border-[var(--line-strong)] bg-[var(--ink-700)] px-3 py-2 text-xs font-semibold text-[var(--paper)] transition-colors duration-150 disabled:opacity-60">Resolve</button>
        </>
      )}
      {status === "ESCALATED" && (
        <button onClick={() => act("resolve")} disabled={pending} className="rounded-lg bg-[var(--evergreen)] px-3 py-2 text-xs font-semibold text-[#06120c] transition-opacity duration-150 disabled:opacity-60">Resolve with evidence</button>
      )}
    </div>
  );
}

function CaseBadge({ status }: { status: ExceptionCaseStatus }) {
  const colors: Record<ExceptionCaseStatus, string> = {
    OPEN: "border-[rgba(227,179,65,0.35)] bg-[rgba(227,179,65,0.14)] text-[var(--amber)]",
    VERIFIED: "border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]",
    ESCALATED: "border-[rgba(95,182,217,0.35)] bg-[rgba(95,182,217,0.14)] text-[var(--sky)]",
    RESOLVED: "border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]",
  };
  const Icon = status === "OPEN" ? Clock3 : Check;
  return <span className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-[9px] font-bold ${colors[status]}`}><Icon size={10} /> {status}</span>;
}
