"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowLeft,
  Beaker,
  Check,
  CircleAlert,
  EyeOff,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";

const LABELS: Record<string, string> = {
  MDR_RATE_INCREASE: "MDR rate increase",
  GST_BASE_CORRUPTION: "GST base corruption",
  DUPLICATE_REFUND_DEDUCTION: "Duplicate refund",
  SETTLEMENT_DELAY: "Settlement delay",
  UNSUPPORTED_FEE: "Unsupported fee",
  FAILED_PAYMENT_SETTLED: "Failed payment settled",
  REFUND_EXCEEDS_PAYMENT: "Refund exceeds payment",
  DUPLICATE_CHARGEBACK_FEE: "Duplicate chargeback fee",
  PAYMENT_METHOD_RECLASSIFICATION: "Method reclassification",
};

export default function MutationTestPage() {
  const { runId } = useParams<{ runId: string }>();
  const mutation = useMutation({ mutationFn: () => api.runMutationTest(runId) });

  useEffect(() => {
    mutation.mutate();
    // Run one isolated suite on first entry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 md:px-8 md:py-9">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[#5e6a64] hover:text-[#1e6b51]"><ArrowLeft size={14} /> Back to control run</Link>
        <section className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><Beaker size={14} /> Financial mutation testing</div>
            <h1 className="text-3xl font-semibold tracking-[-0.035em] md:text-[38px]">Test the controls themselves</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#66716b]">Inject realistic faults into a derived copy, rerun approved controls, and expose what the control suite cannot see.</p>
          </div>
          <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white disabled:opacity-60"><RefreshCw size={15} className={mutation.isPending ? "animate-spin" : ""} /> Run suite again</button>
        </section>

        {mutation.isPending && <div className="panel grid min-h-80 place-items-center rounded-2xl text-center"><div><LoaderCircle className="mx-auto mb-3 animate-spin text-[#1e6b51]" /><p className="text-sm font-medium">Injecting 50 isolated mutations</p><p className="mt-1 text-xs text-[#718079]">Canonical run data remains read-only.</p></div></div>}
        {mutation.isError && <div className="panel rounded-2xl p-8 text-center"><CircleAlert className="mx-auto mb-3 text-[#e86f3a]" /><p className="font-medium">Mutation suite could not be executed.</p></div>}

        {mutation.data && <MutationResults data={mutation.data} />}
      </main>
    </AppShell>
  );
}

function MutationResults({ data }: { data: Awaited<ReturnType<typeof api.runMutationTest>> }) {
  const missed = data.results.filter((result) => !result.detected);
  return <div className="space-y-6">
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Metric icon={Beaker} label="Mutations injected" value={String(data.mutation_count)} />
      <Metric icon={ShieldCheck} label="Detected" value={String(data.detected_count)} tone="green" />
      <Metric icon={EyeOff} label="Missed" value={String(data.missed_count)} tone="orange" />
      <Metric icon={Target} label="Detection rate" value={`${(Number(data.mutation_detection_rate) * 100).toFixed(0)}%`} tone="green" />
      <Metric icon={CircleAlert} label="False positives" value={String(data.false_positive_count)} />
    </section>

    <section className="rounded-2xl border border-[#cbe1d4] bg-[#f4fbf7] p-4">
      <div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg bg-[#dff2e8] text-[#1e6b51]"><Check size={17} /></span><div><p className="text-sm font-semibold">Canonical dataset unchanged</p><p className="mt-0.5 text-xs text-[#62736b]">Every fault ran against a deep derived copy. The source run hash-equivalent serialization is intact.</p></div></div>
    </section>

    <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
      <div className="panel overflow-hidden rounded-2xl">
        <div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Coverage by fault type</h2><p className="mt-1 text-xs text-[#7a847e]">Actual control-engine outcome for each injected class</p></div>
        <div className="divide-y divide-[#e9ece7]">
          {data.coverage.map((item) => {
            const rate = Number(item.detection_rate) * 100;
            return <div key={item.mutation_type} className="px-5 py-3.5">
              <div className="mb-2 flex items-center justify-between gap-4 text-xs"><span className="font-medium">{LABELS[item.mutation_type] ?? item.mutation_type}</span><span className={rate === 100 ? "font-semibold text-[#1e6b51]" : "font-semibold text-[#c25229]"}>{item.detected}/{item.injected} · {rate.toFixed(0)}%</span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-[#edf0eb]"><div className={`h-full rounded-full ${rate === 100 ? "bg-[#2d7a5d]" : "bg-[#e86f3a]"}`} style={{ width: `${rate}%` }} /></div>
            </div>;
          })}
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between"><div><h2 className="text-sm font-semibold">Control blind spots</h2><p className="mt-1 text-xs text-[#7a847e]">Missed mutations requiring governance</p></div><span className="rounded-full bg-[#ffe5d8] px-2.5 py-1 text-[10px] font-bold text-[#bd4d24]">{missed.length} OPEN</span></div>
        <div className="space-y-3">
          {missed.map((item) => <div key={item.id} className="rounded-xl border border-[#efc6b3] bg-[#fff8f4] p-4">
            <div className="mb-3 flex items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#bc5129]">{item.id} · Control blind spot</p><h3 className="mt-1 text-sm font-semibold">{LABELS[item.mutation_type]}</h3></div><X size={16} className="text-[#d45b2e]" /></div>
            <p className="text-xs leading-5 text-[#6f635e]">{item.description}</p>
            <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-[#f0d8cc] pt-3 text-[10px]"><div><dt className="text-[#8c7770]">Expected control</dt><dd className="mt-1 font-mono font-semibold">{item.expected_control_type}</dd></div><div><dt className="text-[#8c7770]">Why missed</dt><dd className="mt-1 font-mono font-semibold">{item.blind_spot_reason}</dd></div></dl>
          </div>)}
        </div>
        <CandidateBacktest />
      </div>
    </section>
  </div>;
}

function CandidateBacktest() {
  const controlId = "CTRL_UNSUPPORTED_FEE_CANDIDATE";
  const backtest = useMutation({ mutationFn: () => api.backtestControl(controlId) });
  const approve = useMutation({ mutationFn: () => api.approveControl(controlId) });
  return <div className="mt-4 rounded-xl border border-[#cbded3] bg-[#f5fbf7] p-4">
    <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#1e6b51]">Draft candidate · Agreement clause 4.6</p><h3 className="mt-1 text-sm font-semibold">Flag every unlisted settlement fee</h3></div><span className="rounded-full bg-[#e5eee8] px-2 py-1 text-[9px] font-bold text-[#52645a]">{approve.isSuccess ? "APPROVED" : "DRAFT"}</span></div>
    {!backtest.data && <><p className="mt-2 text-xs leading-5 text-[#617168]">Test this candidate against historical clean data and the full mutation suite before activation.</p><button onClick={() => backtest.mutate()} disabled={backtest.isPending} className="mt-3 flex items-center gap-2 rounded-lg bg-[#1e6b51] px-3 py-2 text-xs font-semibold text-white disabled:opacity-60">{backtest.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <TrendingUp size={13} />} Backtest candidate</button></>}
    {backtest.data && <div className="mt-4">
      <div className="grid grid-cols-2 gap-3"><div className="rounded-lg border border-[#dfe5e0] bg-white p-3"><p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#77817b]">Before</p><p className="mt-1 text-xl font-semibold">{backtest.data.before.detected_count}/{backtest.data.before.mutation_count}</p><p className="text-[10px] text-[#77817b]">mutations detected</p></div><div className="rounded-lg border border-[#bad8c7] bg-[#ecf8f1] p-3"><p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#1e6b51]">With candidate</p><p className="mt-1 text-xl font-semibold text-[#1e6b51]">{backtest.data.after.detected_count}/{backtest.data.after.mutation_count}</p><p className="text-[10px] text-[#527061]">mutations detected</p></div></div>
      <div className="mt-3 flex justify-between rounded-lg bg-white px-3 py-2 text-[10px]"><span>Detection coverage <strong className="text-[#1e6b51]">+{(Number(backtest.data.detection_rate_delta) * 100).toFixed(0)}%</strong></span><span>False-positive delta <strong>{backtest.data.false_positive_delta}</strong></span></div>
      {!approve.isSuccess && <button onClick={() => approve.mutate()} disabled={approve.isPending} className="mt-3 w-full rounded-lg bg-[#112a2b] px-3 py-2.5 text-xs font-semibold text-white disabled:opacity-60">Approve control</button>}
      {approve.isSuccess && <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-[#1e6b51]"><Check size={13} /> Approved explicitly. Future suites will apply this control.</p>}
    </div>}
  </div>;
}

function Metric({ icon: Icon, label, value, tone = "default" }: { icon: typeof Beaker; label: string; value: string; tone?: "default" | "green" | "orange" }) {
  const colors = { default: "bg-[#edf0eb] text-[#4f5d56]", green: "bg-[#dff2e8] text-[#1e6b51]", orange: "bg-[#ffe5d8] text-[#bd4d24]" };
  return <div className="panel rounded-xl p-4"><span className={`mb-4 grid h-8 w-8 place-items-center rounded-lg ${colors[tone]}`}><Icon size={15} /></span><p className="number-tabular text-2xl font-semibold tracking-[-0.04em]">{value}</p><p className="mt-1 text-[11px] text-[#727d77]">{label}</p></div>;
}
