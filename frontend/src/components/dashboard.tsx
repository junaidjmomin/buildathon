"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Beaker, Check, CircleDollarSign, Clock3, DatabaseZap, FileWarning,
  Fingerprint, LoaderCircle, Play, ScanSearch, ShieldAlert, ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatMoney, formatPercent } from "@/lib/format";

const DEMO_RUN = "RUN_NOVACART_AUG_2026";

export function Dashboard() {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const load = useMutation({
    mutationFn: api.loadDemo,
    onSuccess: (demo) => {
      setRunId(demo.run_id);
      queryClient.invalidateQueries();
    },
  });

  useEffect(() => {
    load.mutate();
    // The seeded demo executes only once when the console opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeRun = runId ?? DEMO_RUN;
  const summary = useQuery({
    queryKey: ["run-summary", activeRun], queryFn: () => api.summary(activeRun), enabled: Boolean(runId),
  });
  const violations = useQuery({
    queryKey: ["violations", activeRun], queryFn: () => api.violations(activeRun), enabled: Boolean(runId),
  });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun], queryFn: () => api.rootCauses(activeRun), enabled: Boolean(runId),
  });

  if (load.isPending || summary.isPending) {
    return (
      <main className="grid min-h-[calc(100vh-64px)] place-items-center p-8 text-center">
        <div><LoaderCircle className="mx-auto mb-4 animate-spin text-[#1e6b51]" size={28} />
          <p className="text-sm font-medium">Running NovaCart controls</p>
          <p className="mt-1 text-xs text-[#66716b]">Rebuilding expected state from the agreement…</p>
        </div>
      </main>
    );
  }

  if (load.isError || summary.isError) {
    return (
      <main className="mx-auto max-w-6xl p-9">
        <div className="panel mt-12 rounded-2xl p-8 text-center">
          <FileWarning className="mx-auto mb-4 text-[#e86f3a]" />
          <h1 className="text-xl font-semibold">The control API is unavailable</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#66716b]">Start FastAPI on port 8000 and retry. Financial results are never simulated in the browser.</p>
          <button onClick={() => load.mutate()} className="mt-5 rounded-lg bg-[#112a2b] px-4 py-2 text-sm font-medium text-white">Retry connection</button>
        </div>
      </main>
    );
  }

  if (!summary.data) return null;
  const data = summary.data;
  const rootMax = Math.max(...(roots.data ?? []).map((root) => Number(root.verified_impact)), 1);

  return (
    <main className="mx-auto max-w-[1440px] px-5 py-7 md:px-8 md:py-9">
      <section className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><Check size={13} /> Run complete</div>
          <h1 className="text-3xl font-semibold tracking-[-0.035em] md:text-[38px]">August control run</h1>
          <p className="mt-2 text-sm text-[#66716b]">Rebuilt expected cash movement across {data.event_count.toLocaleString("en-IN")} financial events.</p>
        </div>
        <button onClick={() => load.mutate()} className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white shadow-lg shadow-[#112a2b]/10 transition hover:-translate-y-0.5">
          <Play size={15} fill="currentColor" /> Run controls again
        </button>
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric icon={DatabaseZap} label="Transactions" value={data.transaction_count.toLocaleString("en-IN")} />
        <Metric icon={Fingerprint} label="Controls evaluated" value={data.control_evaluation_count.toLocaleString("en-IN")} />
        <Metric icon={ShieldCheck} label="Precision" value={formatPercent(data.precision)} tone="green" />
        <Metric icon={ScanSearch} label="Violation recall" value={formatPercent(data.recall)} tone="green" />
        <Metric icon={CircleDollarSign} label="Verified leakage" value={formatMoney(data.verified_leakage, true)} tone="orange" />
        <Metric icon={ShieldAlert} label="Unresolved" value={String(data.unresolved_count)} />
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4">
            <div><h2 className="text-sm font-semibold">Control outcomes</h2><p className="mt-1 text-xs text-[#7a847e]">Payment-level deterministic classification</p></div>
            <span className="rounded-full bg-[#eef1ec] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#66716b]">Ground-truth scored</span>
          </div>
          <div className="grid grid-cols-2 gap-px bg-[#e2e5df] sm:grid-cols-4">
            <Outcome label="Pass" value={data.breakdown.passed} color="#2b8a61" />
            <Outcome label="Violation" value={data.breakdown.violation} color="#e86f3a" />
            <Outcome label="Warning" value={data.breakdown.warning} color="#d6a234" />
            <Outcome label="Unresolved" value={data.breakdown.unresolved} color="#707b75" />
          </div>
          <div className="px-5 py-5">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-[#ecefe9]">
              <div className="bg-[#2b8a61]" style={{ width: `${(data.breakdown.passed / data.transaction_count) * 100}%` }} />
              <div className="bg-[#e86f3a]" style={{ width: `${(data.breakdown.violation / data.transaction_count) * 100}%` }} />
              <div className="bg-[#707b75]" style={{ width: `${(data.breakdown.unresolved / data.transaction_count) * 100}%` }} />
            </div>
            <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2 text-xs text-[#66716b]">
              <span className="flex items-center gap-2"><Clock3 size={13} /> {data.processing_ms} ms processing</span>
              <span>{data.evaluations_per_second.toLocaleString("en-IN")} evaluations/sec</span>
              <span>{formatPercent(data.false_positive_rate)} false-positive rate</span>
            </div>
          </div>
        </div>
        <div className="overflow-hidden rounded-2xl bg-[#112a2b] p-5 text-white shadow-xl shadow-[#112a2b]/10">
          <div className="mb-7 flex items-start justify-between">
            <div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9fceb9]">Cash exposure</p><p className="mt-2 text-3xl font-semibold tracking-[-0.04em]">{formatMoney(data.verified_leakage)}</p></div>
            <CircleDollarSign className="text-[#8fc7ad]" size={22} />
          </div>
          <div className="border-t border-white/10 pt-4">
            <div className="flex items-center justify-between text-xs"><span className="text-white/50">Cash delayed beyond SLA</span><span className="font-medium">{formatMoney(data.cash_delayed, true)}</span></div>
            <p className="mt-4 text-[11px] leading-5 text-white/45">Leakage includes only proven excess deductions. Ambiguous matches stay excluded.</p>
          </div>
        </div>
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <div className="panel rounded-2xl p-5">
          <h2 className="text-sm font-semibold">Root-cause impact</h2>
          <p className="mb-5 mt-1 text-xs text-[#7a847e]">Structural clusters, not repeated symptoms</p>
          <div className="space-y-4">
            {(roots.data ?? []).slice(0, 5).map((root) => (
              <div key={root.id}>
                <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="truncate font-medium">{root.title}</span><span className="number-tabular text-[#66716b]">{formatMoney(root.verified_impact, true)}</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[#edf0eb]"><div className="h-full rounded-full bg-[#2d7a5d]" style={{ width: `${Math.max(4, (Number(root.verified_impact) / rootMax) * 100)}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4">
            <div><h2 className="text-sm font-semibold">Highest-impact exceptions</h2><p className="mt-1 text-xs text-[#7a847e]">Open a transaction to inspect the complete proof</p></div>
            <span className="text-xs font-medium text-[#1e6b51]">{violations.data?.length ?? 0} verified</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="bg-[#f7f8f5] text-[10px] uppercase tracking-[0.11em] text-[#7a847e]"><tr><th className="px-5 py-3">Transaction</th><th className="px-3 py-3">Category</th><th className="px-3 py-3">Expected</th><th className="px-3 py-3">Actual</th><th className="px-3 py-3 text-right">Impact</th><th /></tr></thead>
              <tbody className="divide-y divide-[#ecefe9]">
                {(violations.data ?? []).slice().sort((a, b) => Number(b.financial_impact) - Number(a.financial_impact)).slice(0, 7).map((item) => (
                  <tr key={item.id} className="group hover:bg-[#f9faf7]">
                    <td className="px-5 py-3.5 font-mono text-[11px] font-semibold text-[#1e6b51]">{item.payment_id}</td>
                    <td className="px-3 py-3.5 font-medium">{item.category}</td><td className="px-3 py-3.5 text-[#66716b]">{item.expected}</td><td className="px-3 py-3.5 text-[#b14e29]">{item.actual}</td><td className="number-tabular px-3 py-3.5 text-right font-semibold">{formatMoney(item.financial_impact)}</td>
                    <td className="px-3"><Link href={`/runs/${activeRun}/payments/${item.payment_id}`}><ArrowRight size={15} className="text-[#89928d] group-hover:text-[#1e6b51]" /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <Link href={`/runs/${activeRun}/payments/PAY_82HD9`} className="group flex flex-col justify-between gap-5 rounded-2xl border border-[#efc6b3] bg-[#fff7f2] p-5 transition hover:border-[#e86f3a]/60 md:flex-row md:items-center">
        <div className="flex items-start gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#ffe4d6] text-[#cc5a2c]"><ShieldAlert size={19} /></span><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#bd522a]">Featured proof · PAY_82HD9</p><h3 className="mt-1 text-base font-semibold">Gateway and bank match. The money is still wrong.</h3><p className="mt-1 text-xs leading-5 text-[#765f54]">Inspect the contracted 1.55% MDR against the observed 1.75% deduction.</p></div></div>
        <span className="flex shrink-0 items-center gap-2 text-sm font-semibold text-[#a9431f]">Open financial proof <ArrowRight size={16} className="transition group-hover:translate-x-1" /></span>
      </Link>
      <Link href={`/runs/${activeRun}/mutation-test`} className="group mt-4 flex flex-col justify-between gap-5 rounded-2xl border border-[#cbded3] bg-[#f4fbf7] p-5 transition hover:border-[#2d7a5d]/60 md:flex-row md:items-center">
        <div className="flex items-start gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#dff2e8] text-[#1e6b51]"><Beaker size={19} /></span><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#1e6b51]">Control quality</p><h3 className="mt-1 text-base font-semibold">Would your controls catch the money being wrong?</h3><p className="mt-1 text-xs leading-5 text-[#5e7168]">Inject 50 isolated financial failures and measure real detection coverage.</p></div></div>
        <span className="flex shrink-0 items-center gap-2 text-sm font-semibold text-[#1e6b51]">Test my controls <ArrowRight size={16} className="transition group-hover:translate-x-1" /></span>
      </Link>
    </main>
  );
}

function Metric({ icon: Icon, label, value, tone = "default" }: { icon: typeof DatabaseZap; label: string; value: string; tone?: "default" | "green" | "orange" }) {
  const styles = { default: "bg-[#eef1ec] text-[#45534c]", green: "bg-[#dff2e8] text-[#1e6b51]", orange: "bg-[#fff0e8] text-[#cc5a2c]" };
  return <div className="panel rounded-xl p-4"><div className={`mb-4 grid h-8 w-8 place-items-center rounded-lg ${styles[tone]}`}><Icon size={16} /></div><p className="number-tabular text-[22px] font-semibold tracking-[-0.035em]">{value}</p><p className="mt-1 text-[11px] text-[#727d77]">{label}</p></div>;
}

function Outcome({ label, value, color }: { label: string; value: number; color: string }) {
  return <div className="bg-white px-5 py-4"><div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#77817b]"><span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} /> {label}</div><p className="number-tabular text-2xl font-semibold tracking-[-0.04em]">{value}</p></div>;
}
