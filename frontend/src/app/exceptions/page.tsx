"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, CircleAlert, Clock3, FileCheck2, LoaderCircle, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ExceptionCase, ExceptionCaseStatus } from "@/types/api";

const RUN_ID = "RUN_NOVACART_AUG_2026";

export default function ExceptionsPage() {
  const queryClient = useQueryClient();
  const cases = useQuery({ queryKey: ["exception-cases", RUN_ID], queryFn: () => api.exceptionCases(RUN_ID) });
  const unresolved = useQuery({ queryKey: ["unresolved", RUN_ID], queryFn: () => api.unresolvedMatches(RUN_ID) });
  const transition = useMutation({
    mutationFn: ({ caseId, action, note }: { caseId: string; action: "verify" | "escalate" | "resolve"; note: string }) => api.transitionCase(caseId, action, note),
    onSuccess: (updated) => queryClient.setQueryData<ExceptionCase[]>(["exception-cases", RUN_ID], (current) => current?.map((item) => item.id === updated.id ? updated : item) ?? [updated]),
  });

  if (cases.isPending || unresolved.isPending) return <AppShell><div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[#1e6b51]" /></div></AppShell>;
  const active = cases.data?.[0];
  if (!active) return <AppShell><main className="p-8">No exception cases are available.</main></AppShell>;

  const act = (action: "verify" | "escalate" | "resolve") => {
    const notes = {
      verify: "",
      escalate: "Escalated to the gateway finance owner with the complete evidence pack.",
      resolve: "Recovery acknowledged and case resolved with its evidence trail preserved.",
    };
    transition.mutate({ caseId: active.id, action, note: notes[action] });
  };

  return (
    <AppShell>
      <main className="mx-auto max-w-[1320px] px-5 py-8 md:px-8 md:py-10">
        <section className="mb-7"><p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><FileCheck2 size={14} /> Evidence-backed exceptions</p><h1 className="text-3xl font-semibold tracking-[-0.035em]">Verification becomes an accountable case</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#66716b]">A case cannot skip deterministic verification. Every transition remains in the audit trail.</p></section>

        <section className="mb-6 grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
          <div className="space-y-4">
            <div className="panel rounded-2xl p-5"><div className="flex items-start justify-between"><div><p className="font-mono text-[10px] text-[#718079]">{active.id}</p><h2 className="mt-1 text-base font-semibold">{active.title}</h2><Link href={`/runs/${RUN_ID}/payments/${active.payment_id}`} className="mt-1 flex items-center gap-1 text-xs font-semibold text-[#1e6b51]">{active.payment_id} <ArrowRight size={12} /></Link></div><CaseBadge status={active.status} /></div><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-[#fff3ec] p-3"><p className="text-[9px] uppercase tracking-[0.11em] text-[#a85a3b]">Verified impact</p><p className="mt-1 text-lg font-semibold text-[#a9431f]">{formatMoney(active.verified_impact)}</p></div><div className="rounded-xl bg-[#eef5f0] p-3"><p className="text-[9px] uppercase tracking-[0.11em] text-[#587064]">Evidence items</p><p className="mt-1 text-lg font-semibold text-[#1e6b51]">{active.evidence.length}</p></div></div><CaseActions status={active.status} pending={transition.isPending} act={act} /></div>

            <div className="panel overflow-hidden rounded-2xl"><div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Status audit trail</h2><p className="mt-1 text-xs text-[#78827d]">Append-only reviewer actions</p></div><div className="p-5">{active.audit_trail.map((entry, index) => <div key={`${entry.to_status}-${entry.occurred_at}`} className="flex gap-3"><div className="flex flex-col items-center"><span className="grid h-7 w-7 place-items-center rounded-full bg-[#e5f2eb] text-[#1e6b51]"><Check size={12} /></span>{index < active.audit_trail.length - 1 && <span className="min-h-10 w-px flex-1 bg-[#dce3dd]" />}</div><div className="pb-5"><p className="text-xs font-semibold">{entry.to_status}</p><p className="mt-1 text-[10px] leading-4 text-[#69756e]">{entry.note}</p><p className="mt-1 text-[9px] text-[#8a938e]">{entry.actor} · {new Date(entry.occurred_at).toLocaleString("en-IN")}</p></div></div>)}</div></div>
          </div>

          <div className="panel overflow-hidden rounded-2xl"><div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4"><div><h2 className="text-sm font-semibold">Deterministic evidence pack</h2><p className="mt-1 text-xs text-[#78827d]">Proof required before VERIFIED</p></div><span className="rounded-full bg-[#dff2e8] px-2.5 py-1 text-[10px] font-bold text-[#1e6b51]">{active.evidence.filter((item) => item.verified).length}/{active.evidence.length} VERIFIED</span></div><div className="grid gap-3 p-5 sm:grid-cols-2">{active.evidence.map((item) => <div key={item.id} className="rounded-xl border border-[#dfe5df] bg-[#fafbf8] p-4"><div className="flex items-start justify-between gap-3"><span className="grid h-8 w-8 place-items-center rounded-lg bg-[#e4f2ea] text-[#1e6b51]"><ShieldCheck size={15} /></span><span className="rounded-full bg-[#dff2e8] px-2 py-1 text-[9px] font-bold text-[#1e6b51]">VERIFIED</span></div><p className="mt-3 text-[9px] font-bold uppercase tracking-[0.12em] text-[#758079]">{item.kind}</p><h3 className="mt-1 text-xs font-semibold">{item.title}</h3><p className="mt-2 text-[11px] leading-5 text-[#69756e]">{item.summary}</p><p className="mt-3 border-t border-[#e3e8e2] pt-3 font-mono text-[9px] text-[#7c8680]">{item.source_id}</p></div>)}</div></div>
        </section>

        <section className="panel overflow-hidden rounded-2xl"><div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4"><div><h2 className="text-sm font-semibold">Honest unresolved queue</h2><p className="mt-1 text-xs text-[#78827d]">Ambiguous records are never forced into a match</p></div><span className="rounded-full bg-[#eceeed] px-2.5 py-1 text-[10px] font-bold text-[#66716b]">{unresolved.data?.length ?? 0} UNRESOLVED</span></div><div className="divide-y divide-[#e8ebe6]">{unresolved.data?.map((item) => <div key={item.id} className="flex flex-col justify-between gap-3 px-5 py-4 sm:flex-row sm:items-center"><div><div className="flex items-center gap-2"><CircleAlert size={14} className="text-[#68736d]" /><span className="font-mono text-[10px] font-bold text-[#5d6862]">{item.id}</span><Link href={`/runs/${RUN_ID}/payments/${item.payment_id}`} className="font-mono text-xs font-semibold text-[#1e6b51]">{item.payment_id}</Link><span className="text-xs font-semibold">{formatMoney(item.amount)}</span></div><p className="mt-1 text-[10px] text-[#6d7872]">{item.missing_evidence} {item.safe_conclusion}</p></div><div className="flex gap-2">{item.candidate_bank_references.map((candidate) => <span key={candidate} className="rounded-md bg-[#f0f2ef] px-2 py-1 font-mono text-[9px] text-[#66716b]">{candidate}</span>)}</div></div>)}</div></section>
      </main>
    </AppShell>
  );
}

function CaseActions({ status, pending, act }: { status: ExceptionCaseStatus; pending: boolean; act: (action: "verify" | "escalate" | "resolve") => void }) {
  if (status === "RESOLVED") return <p className="mt-4 flex items-center gap-2 text-xs font-semibold text-[#1e6b51]"><Check size={14} /> Case resolved; evidence and audit history retained.</p>;
  return <div className="mt-4 flex flex-wrap gap-2">{status === "OPEN" && <button onClick={() => act("verify")} disabled={pending} className="flex items-center gap-2 rounded-lg bg-[#1e6b51] px-3 py-2 text-xs font-semibold text-white disabled:opacity-60">{pending ? <LoaderCircle size={13} className="animate-spin" /> : <ShieldCheck size={13} />} Verify evidence</button>}{status === "VERIFIED" && <><button onClick={() => act("escalate")} disabled={pending} className="flex items-center gap-2 rounded-lg bg-[#112a2b] px-3 py-2 text-xs font-semibold text-white"><Send size={13} /> Escalate</button><button onClick={() => act("resolve")} disabled={pending} className="rounded-lg border border-[#cfd9d1] bg-white px-3 py-2 text-xs font-semibold">Resolve</button></>}{status === "ESCALATED" && <button onClick={() => act("resolve")} disabled={pending} className="rounded-lg bg-[#1e6b51] px-3 py-2 text-xs font-semibold text-white">Resolve with evidence</button>}</div>;
}

function CaseBadge({ status }: { status: ExceptionCaseStatus }) {
  const colors: Record<ExceptionCaseStatus, string> = { OPEN: "bg-[#fff0e8] text-[#bd4e24]", VERIFIED: "bg-[#dff2e8] text-[#1e6b51]", ESCALATED: "bg-[#e8edf7] text-[#3e5c91]", RESOLVED: "bg-[#e5f3eb] text-[#1e6b51]" };
  const Icon = status === "OPEN" ? Clock3 : Check;
  return <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[9px] font-bold ${colors[status]}`}><Icon size={10} /> {status}</span>;
}
