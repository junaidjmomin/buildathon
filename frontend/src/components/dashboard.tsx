"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Beaker, Check, CircleDollarSign, Clock3, DatabaseZap, FileWarning,
  Fingerprint, GitBranch, LoaderCircle, Play, ScanSearch, ShieldAlert, ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { useActiveRunId } from "@/lib/active-run";
import { api } from "@/lib/api";
import { compareDecimals, formatMoney, formatPercent } from "@/lib/format";

const DEMO_RUN = "RUN_NOVACART_AUG_2026";
export function Dashboard() {
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const selectedRun = runs.data?.find(
    (run) => run.id === selectedRunId && run.status === "COMPLETE",
  );
  const latestRealRun = runs.data?.find(
    (run) => run.source !== "SEEDED" && run.status === "COMPLETE",
  );
  const load = useQuery({
    queryKey: ["demo-load"],
    queryFn: api.loadDemo,
    enabled: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });
  const activeRunRecord = selectedRun ?? latestRealRun;
  const activeRun = activeRunRecord?.id;
  const activeIsSeeded = activeRunRecord?.source === "SEEDED" || activeRun === DEMO_RUN;
  const summary = useQuery({
    queryKey: ["run-summary", activeRun], queryFn: () => api.summary(activeRun ?? ""), enabled: Boolean(activeRun),
  });
  const violations = useQuery({
    queryKey: ["violations", activeRun], queryFn: () => api.violations(activeRun ?? ""), enabled: Boolean(activeRun),
  });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun], queryFn: () => api.rootCauses(activeRun ?? ""), enabled: Boolean(activeRun),
  });
  const coverage = useQuery({
    queryKey: ["control-coverage", activeRun], queryFn: () => api.controlCoverage(activeRun ?? ""), enabled: activeIsSeeded && Boolean(activeRun),
  });

  if (runs.isPending) {
    return (
      <main className="grid min-h-[calc(100vh-64px)] place-items-center p-8 text-center">
        <div><LoaderCircle className="mx-auto mb-4 animate-spin text-[#1e6b51]" size={28} /><p className="text-sm font-medium">Loading tenant runs</p></div>
      </main>
    );
  }

  if (runs.isError) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8"><div className="panel rounded-2xl p-8 text-center" role="alert"><FileWarning className="mx-auto mb-4 text-[#e86f3a]" /><h1 className="text-xl font-semibold">Runs could not be loaded</h1><p className="mt-2 text-sm text-[#66716b]">Retry after checking the authenticated API connection.</p><button className="mt-5 rounded-lg bg-[#112a2b] px-4 py-2 text-sm font-medium text-white" onClick={() => void runs.refetch()}>Retry</button></div></main>
    );
  }

  if (!activeRun) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <div className="panel rounded-2xl p-8 md:p-12">
          <ShieldCheck className="mb-5 text-[#1e6b51]" size={30} />
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">Financial control workspace</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">No completed control run</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#66716b]">Upload an accepted source bundle or connect Razorpay to start an explicit, auditable run.</p>
          <Link href="/data" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white">Open data sources <ArrowRight size={15} /></Link>
        </div>
      </main>
    );
  }

  if (summary.isPending) {
    return (
      <main className="grid min-h-[calc(100vh-64px)] place-items-center p-8 text-center">
        <div><LoaderCircle className="mx-auto mb-4 animate-spin text-[#1e6b51]" size={28} />
          <p className="text-sm font-medium">Loading the selected control run</p>
          <p className="mt-1 text-xs text-[#66716b]">Reading tenant-scoped deterministic results…</p>
        </div>
      </main>
    );
  }

  if (summary.isError) {
    return (
      <main className="mx-auto max-w-6xl p-9">
        <div className="panel mt-12 rounded-2xl p-8 text-center">
          <FileWarning className="mx-auto mb-4 text-[#e86f3a]" />
          <h1 className="text-xl font-semibold">The control API is unavailable</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#66716b]">The authenticated run summary could not be loaded. No unavailable financial value has been replaced with demo data.</p>
          <button onClick={() => void summary.refetch()} className="mt-5 rounded-lg bg-[#112a2b] px-4 py-2 text-sm font-medium text-white">Retry connection</button>
        </div>
      </main>
    );
  }

  if (violations.isError || roots.isError || coverage.isError) {
    return (
      <main className="mx-auto max-w-6xl p-9">
        <div className="panel mt-12 rounded-2xl p-8 text-center" role="alert">
          <FileWarning className="mx-auto mb-4 text-[#e86f3a]" />
          <h1 className="text-xl font-semibold">The run is only partially available</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#66716b]">At least one financial evidence section failed to load. No unavailable value has been replaced with zero.</p>
          <button onClick={() => queryClient.invalidateQueries()} className="mt-5 rounded-lg bg-[#112a2b] px-4 py-2 text-sm font-medium text-white">Retry all evidence</button>
        </div>
      </main>
    );
  }

  if (!summary.data) return null;
  const data = summary.data;
  const rootMax = Math.max(...(roots.data ?? []).map((root) => Number(root.verified_impact)), 1);
  const primaryCount = (roots.data ?? []).reduce((total, root) => total + root.primary_violation_count, 0);
  const downstreamCount = (roots.data ?? []).reduce((total, root) => total + root.downstream_effect_count, 0);
  const outcomeTotal = Math.max(
    data.breakdown.passed +
      data.breakdown.violation +
      data.breakdown.warning +
      data.breakdown.unresolved,
    1,
  );

  return (
    <main className="mx-auto max-w-[1440px] px-5 py-7 md:px-8 md:py-9">
      <section className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><Check size={13} /> Run complete</div>
          <h1 className="text-3xl font-semibold tracking-[-0.035em] md:text-[38px]">{data.name}</h1>
          <p className="mt-2 text-sm text-[#66716b]">Rebuilt expected cash movement across {data.event_count.toLocaleString("en-IN")} financial events.</p>
        </div>
        {activeIsSeeded ? <button onClick={() => void load.refetch().then(() => queryClient.invalidateQueries({ queryKey: ["run-summary", DEMO_RUN] }))} disabled={load.isFetching} className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white shadow-lg shadow-[#112a2b]/10 transition hover:-translate-y-0.5 disabled:opacity-60"><Play size={15} fill="currentColor" /> {load.isFetching ? "Running controls…" : "Run controls again"}</button> : <Link href="/data" className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white">Create another run <ArrowRight size={15} /></Link>}
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <Metric icon={DatabaseZap} label="Transactions" value={data.transaction_count.toLocaleString("en-IN")} />
        <Metric icon={Fingerprint} label="Controls evaluated" value={data.control_evaluation_count.toLocaleString("en-IN")} />
        <Metric icon={ShieldCheck} label="Precision" value={data.ground_truth_available ? formatPercent(data.precision) : "Not scored"} tone="green" />
        <Metric icon={ScanSearch} label="Violation recall" value={data.ground_truth_available ? formatPercent(data.recall) : "Not scored"} tone="green" />
        <Metric icon={CircleDollarSign} label="Verified leakage" value={formatMoney(data.verified_leakage, true)} tone="orange" />
        <Metric icon={ShieldAlert} label="Unresolved" value={String(data.unresolved_count)} />
        <Metric icon={ShieldCheck} label="Control coverage" value={coverage.data ? formatPercent(coverage.data.coverage_percentage) : "Not measured"} tone="green" />
        <Metric icon={GitBranch} label="Primary / downstream" value={`${primaryCount} / ${downstreamCount}`} />
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4">
            <div><h2 className="text-sm font-semibold">Control outcomes</h2><p className="mt-1 text-xs text-[#7a847e]">{data.ground_truth_available ? "Seeded payment-level deterministic classification" : "Deterministic control-evaluation outcomes; no labeled ground truth"}</p></div>
            <span className="rounded-full bg-[#eef1ec] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#66716b]">{data.ground_truth_available ? "Ground-truth scored" : "Live control outcomes"}</span>
          </div>
          <div className="grid grid-cols-2 gap-px bg-[#e2e5df] sm:grid-cols-4">
            <Outcome label="Pass" value={data.breakdown.passed} color="#2b8a61" />
            <Outcome label="Violation" value={data.breakdown.violation} color="#e86f3a" />
            <Outcome label="Warning" value={data.breakdown.warning} color="#d6a234" />
            <Outcome label="Unresolved" value={data.breakdown.unresolved} color="#707b75" />
          </div>
          <div className="px-5 py-5">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-[#ecefe9]">
              <div className="bg-[#2b8a61]" style={{ width: `${(data.breakdown.passed / outcomeTotal) * 100}%` }} />
              <div className="bg-[#e86f3a]" style={{ width: `${(data.breakdown.violation / outcomeTotal) * 100}%` }} />
              <div className="bg-[#d6a234]" style={{ width: `${(data.breakdown.warning / outcomeTotal) * 100}%` }} />
              <div className="bg-[#707b75]" style={{ width: `${(data.breakdown.unresolved / outcomeTotal) * 100}%` }} />
            </div>
            <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2 text-xs text-[#66716b]">
              <span className="flex items-center gap-2"><Clock3 size={13} /> {data.processing_ms} ms processing</span>
              <span>{data.evaluations_per_second.toLocaleString("en-IN")} evaluations/sec</span>
              <span>{data.ground_truth_available ? `${formatPercent(data.false_positive_rate)} false-positive rate` : "Ground-truth metrics unavailable for live data"}</span>
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
              <Link href={`/root-causes/${root.id}`} key={root.id} className="block rounded-lg p-1 transition hover:bg-[#f5f7f3]">
                <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="truncate font-medium">{root.title}</span><span className="number-tabular text-[#66716b]">{formatMoney(root.verified_impact, true)}</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[#edf0eb]"><div className="h-full rounded-full bg-[#2d7a5d]" style={{ width: `${Math.max(4, (Number(root.verified_impact) / rootMax) * 100)}%` }} /></div>
              </Link>
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
                {(violations.data ?? []).slice().sort((a, b) => compareDecimals(b.financial_impact, a.financial_impact)).slice(0, 7).map((item) => (
                  <tr key={item.id} className="group hover:bg-[#f9faf7]">
                    <td className="px-5 py-3.5 font-mono text-[11px] font-semibold text-[#1e6b51]">{item.payment_id}</td>
                    <td className="px-3 py-3.5 font-medium">{item.category}</td><td className="px-3 py-3.5 text-[#66716b]">{item.expected}</td><td className="px-3 py-3.5 text-[#b14e29]">{item.actual}</td><td className="number-tabular px-3 py-3.5 text-right font-semibold">{formatMoney(item.financial_impact)}</td>
                    <td className="px-3">{activeIsSeeded ? <Link href={`/runs/${activeRun}/payments/${item.payment_id}`}><ArrowRight size={15} className="text-[#89928d] group-hover:text-[#1e6b51]" /></Link> : item.root_cause_id ? <Link href={`/root-causes/${item.root_cause_id}`} aria-label={`Open root cause for ${item.payment_id}`}><ArrowRight size={15} className="text-[#89928d] group-hover:text-[#1e6b51]" /></Link> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {activeIsSeeded ? <><Link href={`/runs/${activeRun}/payments/PAY_82HD9`} className="group flex flex-col justify-between gap-5 rounded-2xl border border-[#efc6b3] bg-[#fff7f2] p-5 transition hover:border-[#e86f3a]/60 md:flex-row md:items-center">
        <div className="flex items-start gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#ffe4d6] text-[#cc5a2c]"><ShieldAlert size={19} /></span><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#bd522a]">Featured proof · PAY_82HD9</p><h3 className="mt-1 text-base font-semibold">Gateway and bank match. The money is still wrong.</h3><p className="mt-1 text-xs leading-5 text-[#765f54]">Inspect the contracted 1.55% MDR against the observed 1.75% deduction.</p></div></div>
        <span className="flex shrink-0 items-center gap-2 text-sm font-semibold text-[#a9431f]">Open financial proof <ArrowRight size={16} className="transition group-hover:translate-x-1" /></span>
      </Link>
      <Link href={`/runs/${activeRun}/mutation-test`} className="group mt-4 flex flex-col justify-between gap-5 rounded-2xl border border-[#cbded3] bg-[#f4fbf7] p-5 transition hover:border-[#2d7a5d]/60 md:flex-row md:items-center">
        <div className="flex items-start gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#dff2e8] text-[#1e6b51]"><Beaker size={19} /></span><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#1e6b51]">Control quality</p><h3 className="mt-1 text-base font-semibold">Would your controls catch the money being wrong?</h3><p className="mt-1 text-xs leading-5 text-[#5e7168]">Inject 50 isolated financial failures and measure real detection coverage.</p></div></div>
        <span className="flex shrink-0 items-center gap-2 text-sm font-semibold text-[#1e6b51]">Test my controls <ArrowRight size={16} className="transition group-hover:translate-x-1" /></span>
      </Link></> : <section className="rounded-2xl border border-[#cbded3] bg-[#f4fbf7] p-5"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#1e6b51]">Live source verification</p><h3 className="mt-1 text-base font-semibold">Uploaded or connected-source evidence has been tested against approved controls.</h3><p className="mt-1 text-xs leading-5 text-[#5e7168]">Open a root cause to run the bounded investigation trace, or create another immutable run.</p><div className="mt-4 flex flex-wrap gap-3">{roots.data?.[0] ? <Link href={`/root-causes/${roots.data[0].id}`} className="inline-flex items-center gap-2 rounded-lg bg-[#112a2b] px-3 py-2 text-xs font-semibold text-white">Investigate root cause <ArrowRight size={13} /></Link> : null}<Link href="/data" className="inline-flex items-center gap-2 rounded-lg border border-[#cbded3] bg-white px-3 py-2 text-xs font-semibold">Open data sources</Link></div></section>}
      <section className="mt-4 grid gap-3 md:grid-cols-3">
        <QuickLink href="/agreements" label="Agreement provenance" detail="Clause → typed control → immutable version" />
        {activeIsSeeded ? <QuickLink href={`/runs/${activeRun}/coverage`} label="Control coverage" detail="Measure governed and ungoverned money edges" /> : <QuickLink href="/data" label="Source provenance" detail="Immutable snapshots, checksums and sync job status" />}
        {activeIsSeeded ? <QuickLink href="/exceptions" label="Evidence cases" detail="Verify, escalate or resolve with an audit trail" /> : roots.data?.[0] ? <QuickLink href={`/root-causes/${roots.data[0].id}`} label="Root-cause evidence" detail="Open the deterministic cluster and investigation trace" /> : <QuickLink href="/data" label="No root cause yet" detail="Sync evidence and run deterministic controls" />}
      </section>
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

function QuickLink({ href, label, detail }: { href: string; label: string; detail: string }) {
  return <Link href={href} className="panel group flex items-center justify-between rounded-xl p-4"><div><p className="text-xs font-semibold">{label}</p><p className="mt-1 text-[10px] text-[#727d77]">{detail}</p></div><ArrowRight size={14} className="text-[#89928d] transition group-hover:translate-x-1 group-hover:text-[#1e6b51]" /></Link>;
}
