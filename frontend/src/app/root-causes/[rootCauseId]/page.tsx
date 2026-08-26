"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, BrainCircuit, CircleDollarSign, GitBranch, LoaderCircle, Scale, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function RootCausePage() {
  const { rootCauseId } = useParams<{ rootCauseId: string }>();
  const root = useQuery({ queryKey: ["root-cause", rootCauseId], queryFn: () => api.rootCause(rootCauseId) });
  const hypothesis = useMutation({ mutationFn: () => api.generateHypothesis(rootCauseId) });
  const verification = useMutation({ mutationFn: () => api.verifyHypothesis(rootCauseId) });

  if (root.isPending) return <AppShell><div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[#1e6b51]" /></div></AppShell>;
  if (!root.data) return <AppShell><main className="p-8">Root cause could not be loaded.</main></AppShell>;
  const data = root.data;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[#5e6a64]"><ArrowLeft size={14} /> Back to control run</Link>
        <section className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><GitBranch size={14} /> Systemic root cause</p><h1 className="text-3xl font-semibold tracking-[-0.035em]">{data.title}</h1><p className="mt-2 text-sm text-[#66716b]">{data.category} · {data.id}</p></div><div className="rounded-xl border border-[#efc6b3] bg-[#fff5ef] px-5 py-3 text-right"><p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#b95a35]">Verified impact</p><p className="mt-1 text-2xl font-semibold text-[#a9431f]">{formatMoney(data.verified_impact)}</p></div></section>

        <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric icon={ShieldAlert} label="Affected payments" value={String(data.affected_count)} /><Metric icon={GitBranch} label="Primary violations" value={String(data.primary_violation_count)} /><Metric icon={GitBranch} label="Downstream effects" value={String(data.downstream_effect_count)} /><Metric icon={CircleDollarSign} label="Expected → observed" value={`${data.expected_value} → ${data.observed_value}`} /></section>

        <section className="grid gap-5 lg:grid-cols-2">
          <div className="panel overflow-hidden rounded-2xl"><div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="flex items-center gap-2 text-sm font-semibold"><BrainCircuit size={16} className="text-[#1e6b51]" /> AI investigator</h2><p className="mt-1 text-xs text-[#78827d]">Pattern discovery only—no financial verdict</p></div><div className="p-5">{!hypothesis.data ? <><p className="text-xs leading-6 text-[#66716b]">The investigator may propose a structured explanation for the repeated 1.75% observation. It cannot change the approved expectation.</p><button onClick={() => hypothesis.mutate()} disabled={hypothesis.isPending} className="mt-4 flex items-center gap-2 rounded-lg bg-[#112a2b] px-3 py-2.5 text-xs font-semibold text-white disabled:opacity-60">{hypothesis.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <BrainCircuit size={13} />} Generate bounded hypothesis</button></> : <><div className="rounded-xl border border-[#dfe5df] bg-[#f8faf7] p-4"><p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#6b7770]">AI HYPOTHESIS · {hypothesis.data.status}</p><p className="mt-2 text-sm font-medium leading-6">“{hypothesis.data.hypothesis}”</p></div><p className="mt-3 text-[10px] leading-5 text-[#6c7771]">This statement is evidence-seeking output, not truth. The deterministic verifier must challenge it.</p>{!verification.data && <button onClick={() => verification.mutate()} disabled={verification.isPending} className="mt-4 flex items-center gap-2 rounded-lg bg-[#1e6b51] px-3 py-2.5 text-xs font-semibold text-white disabled:opacity-60">{verification.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Scale size={13} />} Verify independently</button>}</>}</div></div>

          <div className={`overflow-hidden rounded-2xl border ${verification.data ? "border-[#efc6b3] bg-[#fff8f4]" : "border-[#dfe4df] bg-white"}`}><div className="border-b border-black/5 px-5 py-4"><h2 className="flex items-center gap-2 text-sm font-semibold"><Scale size={16} className="text-[#1e6b51]" /> Deterministic verifier</h2><p className="mt-1 text-xs text-[#78827d]">Agreement, amendments, effective dates and comparison segments</p></div><div className="p-5">{!verification.data ? <div className="grid min-h-52 place-items-center text-center"><div><Scale className="mx-auto mb-3 text-[#a6afa9]" /><p className="text-sm font-medium">Awaiting a hypothesis</p><p className="mt-1 text-xs text-[#78827d]">No conclusion is inferred in advance.</p></div></div> : <><div className="mb-4 flex items-center justify-between rounded-xl bg-[#ffe5d8] p-4"><div><p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#a95231]">VERIFIER RESULT</p><p className="mt-1 text-xl font-semibold text-[#a9431f]">{verification.data.status}</p></div><X size={22} className="text-[#c55329]" /></div><div className="space-y-2">{verification.data.checks.map((check) => <div key={check.label} className="flex items-center justify-between gap-3 rounded-lg border border-[#eadfd9] bg-white px-3 py-2.5"><div><p className="text-[10px] text-[#7a847e]">{check.label}</p><p className="mt-0.5 text-xs font-medium">{check.value}</p></div><span className={`text-[9px] font-bold ${check.result === "DEVIATION" || check.result === "NOT_EFFECTIVE" ? "text-[#bd4e24]" : "text-[#1e6b51]"}`}>{check.result}</span></div>)}</div><div className="mt-4 border-t border-[#efdcd2] pt-4"><p className="text-xs font-semibold">{verification.data.classification.replaceAll("_", " ")}</p><p className="mt-1 text-xs leading-5 text-[#745f55]">{verification.data.conclusion}</p></div></>}</div></div>
        </section>
      </main>
    </AppShell>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof ShieldAlert; label: string; value: string }) {
  return <div className="panel rounded-xl p-4"><Icon size={15} className="mb-4 text-[#1e6b51]" /><p className="number-tabular text-lg font-semibold tracking-[-0.025em]">{value}</p><p className="mt-1 text-[11px] text-[#727d77]">{label}</p></div>;
}
