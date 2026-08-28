"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Beaker, Check, CircleDollarSign, Clock3, DatabaseZap, FileWarning,
  Fingerprint, LoaderCircle, Play, ScanSearch, ShieldAlert, ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { resolveActiveRun, useActiveRunId, useActiveRunOverride } from "@/lib/active-run";
import { api } from "@/lib/api";
import { compareDecimals, formatMoney, formatPercent } from "@/lib/format";

function decimalCents(value: string): bigint {
  const [whole, fraction = ""] = value.split(".");
  return BigInt(`${whole || "0"}${fraction.padEnd(2, "0").slice(0, 2)}`);
}

function ratioPercent(value: string, maximum: string): number {
  const max = decimalCents(maximum);
  if (max <= BigInt(0)) return 0;
  return Number((decimalCents(value) * BigInt(10000)) / max) / 100;
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const selectedRunId = useActiveRunId();
  const isOverride = useActiveRunOverride();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const load = useQuery({
    queryKey: ["demo-load"],
    queryFn: api.loadDemo,
    enabled: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });
  const exportEvidence = useMutation({
    mutationFn: () => api.exportEvidence(activeRun ?? ""),
  });
  const activeRunRecord = resolveActiveRun(runs.data, selectedRunId, {
    allowSeeded: isOverride,
  });
  const activeRun = activeRunRecord?.id;
  const activeIsSeeded = activeRunRecord?.source_type === "DEMO";
  const summary = useQuery({
    queryKey: ["run-summary", activeRun], queryFn: () => api.summary(activeRun ?? ""), enabled: Boolean(activeRun),
    placeholderData: (previous) => previous,
  });
  const violations = useQuery({
    queryKey: ["violations", activeRun], queryFn: () => api.violations(activeRun ?? ""), enabled: Boolean(activeRun),
  });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun], queryFn: () => api.rootCauses(activeRun ?? ""), enabled: Boolean(activeRun),
  });
  if (runs.isPending) {
    return (
      <main className="grid min-h-[calc(100vh-64px)] place-items-center p-8 text-center">
        <div><LoaderCircle className="mx-auto mb-4 animate-spin text-[var(--evergreen)]" size={28} /><p className="text-sm font-medium">Loading tenant runs</p></div>
      </main>
    );
  }

  if (runs.isError) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8"><div className="panel rounded-2xl p-8 text-center" role="alert"><FileWarning className="mx-auto mb-4 text-[var(--crimson)]" /><h1 className="text-xl font-semibold">Runs could not be loaded</h1><p className="mt-2 text-sm text-[var(--paper-dim)]">Retry after checking the authenticated API connection.</p><button className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2 text-sm font-medium text-[#06120c]" onClick={() => void runs.refetch()}>Retry</button></div></main>
    );
  }

  if (!activeRun) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <div className="panel rounded-2xl p-8 md:p-12">
          <ShieldCheck className="mb-5 text-[var(--evergreen)]" size={30} />
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--evergreen)]">Financial control workspace</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">No completed control run</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--paper-dim)]">Upload an accepted source bundle or connect Razorpay to start an explicit, auditable run.</p>
          <Link href="/data" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[var(--evergreen)] px-4 py-3 text-sm font-medium text-[#06120c] transition duration-150 hover:-translate-y-0.5">Open data sources <ArrowRight size={15} /></Link>
        </div>
      </main>
    );
  }

  if (summary.isPending) {
    return (
      <main className="grid min-h-[calc(100vh-64px)] place-items-center p-8 text-center">
        <div><LoaderCircle className="mx-auto mb-4 animate-spin text-[var(--evergreen)]" size={28} />
          <p className="text-sm font-medium">Loading the selected control run</p>
          <p className="mt-1 text-xs text-[var(--paper-dim)]">Reading tenant-scoped deterministic results…</p>
        </div>
      </main>
    );
  }

  if (summary.isError) {
    return (
      <main className="mx-auto max-w-6xl p-9">
        <div className="panel mt-12 rounded-2xl p-8 text-center">
          <FileWarning className="mx-auto mb-4 text-[var(--crimson)]" />
          <h1 className="text-xl font-semibold">The control API is unavailable</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--paper-dim)]">The authenticated run summary could not be loaded. No unavailable financial value has been replaced with demo data.</p>
          <button onClick={() => void summary.refetch()} className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2 text-sm font-medium text-[#06120c]">Retry connection</button>
        </div>
      </main>
    );
  }

  if (violations.isError || roots.isError) {
    return (
      <main className="mx-auto max-w-6xl p-9">
        <div className="panel mt-12 rounded-2xl p-8 text-center" role="alert">
          <FileWarning className="mx-auto mb-4 text-[var(--crimson)]" />
          <h1 className="text-xl font-semibold">The run is only partially available</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--paper-dim)]">At least one financial evidence section failed to load. No unavailable value has been replaced with zero.</p>
          <button onClick={() => queryClient.invalidateQueries()} className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2 text-sm font-medium text-[#06120c]">Retry all evidence</button>
        </div>
      </main>
    );
  }

  if (!summary.data) return null;
  const data = summary.data;
  const featuredViolation = violations.data?.find((item) => item.category === "MDR rate deviation");
  const rootMax = (roots.data ?? []).reduce(
    (maximum, root) => (compareDecimals(root.verified_impact, maximum) > 0 ? root.verified_impact : maximum),
    "0",
  );
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
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--evergreen)]"><Check size={13} /> Run complete</div>
          <h1 className="text-3xl font-semibold tracking-[-0.035em] text-[var(--paper)] md:text-[38px]">{data.name}</h1>
          <p className="mt-2 text-sm text-[var(--paper-dim)]">Rebuilt expected cash movement across {data.event_count.toLocaleString("en-IN")} financial events.</p>
        </div>
        {activeIsSeeded ? <button onClick={() => void load.refetch().then(() => queryClient.invalidateQueries({ queryKey: ["run-summary", activeRun] }))} disabled={load.isFetching} className="flex items-center justify-center gap-2 rounded-xl bg-[var(--evergreen)] px-4 py-3 text-sm font-medium text-[#06120c] transition duration-150 hover:-translate-y-0.5 disabled:opacity-60"><Play size={15} fill="currentColor" /> {load.isFetching ? "Running controls…" : "Run controls again"}</button> : <Link href="/data" className="flex items-center justify-center gap-2 rounded-xl bg-[var(--evergreen)] px-4 py-3 text-sm font-medium text-[#06120c] transition duration-150 hover:-translate-y-0.5">Create another run <ArrowRight size={15} /></Link>}
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <Metric icon={DatabaseZap} label="Transactions" value={data.transaction_count.toLocaleString("en-IN")} href="/data" />
        <Metric icon={Fingerprint} label="Controls evaluated" value={data.control_evaluation_count.toLocaleString("en-IN")} />
        <Metric icon={CircleDollarSign} label="Verified leakage" value={formatMoney(data.verified_leakage, true)} tone="crimson" href="/exceptions" />
        <Metric icon={ShieldAlert} label="Unresolved" value={String(data.unresolved_count)} href="/exceptions" />
        <Metric icon={ShieldCheck} label="Control coverage" value={data.control_coverage != null ? formatPercent(data.control_coverage) : "Not measured"} tone="green" href={`/runs/${activeRun}/coverage`} />
        <Metric icon={ScanSearch} label={data.ground_truth_available ? "Precision" : "Run status"} value={data.ground_truth_available ? formatPercent(data.precision) : "Live"} tone="green" />
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
            <div><h2 className="text-sm font-semibold text-[var(--paper)]">Control outcomes</h2><p className="mt-1 text-xs text-[var(--paper-faint)]">{data.ground_truth_available ? "Seeded payment-level deterministic classification" : "Deterministic control-evaluation outcomes; no labeled ground truth"}</p></div>
            <span className="rounded-full border border-[var(--line-strong)] bg-[var(--ink-600)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--paper-dim)]">{data.ground_truth_available ? "Ground-truth scored" : "Live control outcomes"}</span>
          </div>
          <div className="grid grid-cols-2 gap-px bg-[var(--line)] sm:grid-cols-4">
            <Outcome label="Pass" value={data.breakdown.passed} color="var(--evergreen)" />
            <Outcome label="Violation" value={data.breakdown.violation} color="var(--crimson)" />
            <Outcome label="Warning" value={data.breakdown.warning} color="var(--amber)" />
            <Outcome label="Unresolved" value={data.breakdown.unresolved} color="var(--paper-faint)" />
          </div>
          <div className="px-5 py-5">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-[var(--ink-600)]">
              <div className="bg-[var(--evergreen)]" style={{ width: `${(data.breakdown.passed / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--crimson)]" style={{ width: `${(data.breakdown.violation / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--amber)]" style={{ width: `${(data.breakdown.warning / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--paper-faint)]" style={{ width: `${(data.breakdown.unresolved / outcomeTotal) * 100}%` }} />
            </div>
            <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2 text-xs text-[var(--paper-dim)]">
              <span className="flex items-center gap-2"><Clock3 size={13} /> {formatDuration(data.processing_ms)} processing</span>
              <span className="number-tabular font-mono">{data.evaluations_per_second.toLocaleString("en-IN")} evaluations/sec</span>
              <span>{data.ground_truth_available ? `${formatPercent(data.false_positive_rate)} false-positive rate` : "Ground-truth metrics unavailable for live data"}</span>
            </div>
          </div>
        </div>
        <Link href="/exceptions" className="block overflow-hidden rounded-2xl border border-[rgba(47,189,127,0.28)] bg-[linear-gradient(150deg,var(--ink-700),var(--ink-800))] p-5 shadow-xl shadow-black/30 transition-colors hover:border-[var(--evergreen)]">
          <div className="mb-7 flex items-start justify-between">
            <div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--evergreen)]">Cash exposure</p><p className="number-tabular mt-2 font-mono text-3xl font-semibold tracking-[-0.04em] text-[var(--paper)]">{formatMoney(data.verified_leakage)}</p></div>
            <CircleDollarSign className="text-[var(--evergreen)]" size={22} />
          </div>
          <div className="border-t border-[var(--line-strong)] pt-4">
            <div className="flex items-center justify-between text-xs"><span className="text-[var(--paper-dim)]">Cash delayed beyond SLA</span><span className="number-tabular font-mono font-medium text-[var(--paper)]">{formatMoney(data.cash_delayed, true)}</span></div>
            <p className="mt-4 text-[11px] leading-5 text-[var(--paper-faint)]">Leakage includes only proven excess deductions. Ambiguous matches stay excluded.</p>
          </div>
        </Link>
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <div className="panel rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--paper)]">Root-cause impact</h2>
          <p className="mb-5 mt-1 text-xs text-[var(--paper-faint)]">Structural clusters, not repeated symptoms</p>
          <div className="max-h-52 space-y-4 overflow-y-auto pr-1">
            {(roots.data ?? []).slice(0, 5).map((root) => (
              <Link href={`/root-causes/${root.id}`} key={root.id} className="block rounded-lg p-1 transition-colors hover:bg-[var(--ink-600)]">
                <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="truncate font-medium text-[var(--paper)]">{root.title}</span><span className="number-tabular font-mono text-[var(--paper-dim)]">{formatMoney(root.verified_impact, true)}</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ink-600)]"><div className="h-full rounded-full bg-[var(--evergreen)]" style={{ width: `${Math.max(4, ratioPercent(root.verified_impact, rootMax))}%` }} /></div>
              </Link>
            ))}
          </div>
        </div>
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
            <div><h2 className="text-sm font-semibold text-[var(--paper)]">Highest-impact exceptions</h2><p className="mt-1 text-xs text-[var(--paper-faint)]">Open a transaction to inspect the complete proof</p></div>
            <Link href="/exceptions" className="text-xs font-medium text-[var(--evergreen)] hover:underline">View all · {violations.data?.length ?? 0} verified</Link>
          </div>
          <div className="max-h-72 overflow-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="bg-[var(--ink-700)] text-[10px] uppercase tracking-[0.11em] text-[var(--paper-faint)]"><tr><th className="px-5 py-3">Transaction</th><th className="px-3 py-3">Category</th><th className="px-3 py-3">Expected</th><th className="px-3 py-3">Actual</th><th className="px-3 py-3 text-right">Impact</th><th /></tr></thead>
              <tbody className="divide-y divide-[var(--line)]">
                {(violations.data ?? []).slice().sort((a, b) => compareDecimals(b.financial_impact, a.financial_impact)).slice(0, 6).map((item) => (
                  <tr key={item.id} className="group transition-colors hover:bg-[var(--ink-600)]">
                    <td className="number-tabular px-5 py-3.5 font-mono text-[11px] font-semibold text-[var(--evergreen)]">{item.payment_id}</td>
                    <td className="px-3 py-3.5 font-medium text-[var(--paper)]">{item.category}</td><td className="px-3 py-3.5 text-[var(--paper-dim)]">{item.expected}</td><td className="px-3 py-3.5 text-[var(--crimson)]">{item.actual}</td><td className="number-tabular px-3 py-3.5 text-right font-mono font-semibold text-[var(--paper)]">{formatMoney(item.financial_impact)}</td>
                    <td className="px-3">{activeIsSeeded ? <Link href={`/runs/${activeRun}/payments/${item.payment_id}`}><ArrowRight size={15} className="text-[var(--paper-faint)] transition-colors group-hover:text-[var(--evergreen)]" /></Link> : item.root_cause_id ? <Link href={`/root-causes/${item.root_cause_id}`} aria-label={`Open root cause for ${item.payment_id}`}><ArrowRight size={15} className="text-[var(--paper-faint)] transition-colors group-hover:text-[var(--evergreen)]" /></Link> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="mt-5 rounded-2xl border border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.06)] p-5">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div className="flex items-start gap-4">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[rgba(47,189,127,0.16)] text-[var(--evergreen)]"><Beaker size={19} /></span>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--evergreen)]">Recommended next action</p>
              <h3 className="mt-1 text-base font-semibold text-[var(--paper)]">{activeIsSeeded && featuredViolation ? `Inspect ${featuredViolation.payment_id} financial proof` : "Validate this run’s control quality"}</h3>
              <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{activeIsSeeded ? "Start with the highest-signal exception, then open deeper lineage or mutation evidence only if needed." : "Run deterministic mutations or investigate the leading root cause before exporting evidence."}</p>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {activeIsSeeded && featuredViolation ? <Link href={`/runs/${activeRun}/payments/${featuredViolation.payment_id}`} className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2 text-xs font-semibold text-[#06120c]">Open proof <ArrowRight size={13} /></Link> : <Link href={`/runs/${activeRun}/mutation-test`} className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2 text-xs font-semibold text-[#06120c]">Run mutation test <ArrowRight size={13} /></Link>}
            {roots.data?.[0] ? <Link href={`/root-causes/${roots.data[0].id}`} className="inline-flex items-center gap-2 rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold text-[var(--paper)]">Root cause <ArrowRight size={13} /></Link> : null}
          </div>
        </div>
        {exportEvidence.data ? <p className="mt-3 text-[10px] text-[var(--evergreen)]">Evidence pack stored privately as {exportEvidence.data.artifact_id}.</p> : exportEvidence.isError ? <p className="mt-3 text-[10px] text-[var(--crimson)]">Evidence export is unavailable until private Storage is configured.</p> : null}
      </section>
    </main>
  );
}

function formatDuration(milliseconds: number): string {
  if (milliseconds >= 1000) return `${(milliseconds / 1000).toFixed(milliseconds >= 10_000 ? 1 : 2)} s`;
  return `${milliseconds} ms`;
}

function Metric({ icon: Icon, label, value, tone = "default", href }: { icon: typeof DatabaseZap; label: string; value: string; tone?: "default" | "green" | "crimson"; href?: string }) {
  const styles = {
    default: "bg-[var(--ink-600)] text-[var(--paper-dim)]",
    green: "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]",
    crimson: "bg-[rgba(226,96,79,0.14)] text-[var(--crimson)]",
  };
  const content = <><div className={`mb-4 grid h-8 w-8 place-items-center rounded-lg ${styles[tone]}`}><Icon size={16} /></div><p className="number-tabular font-mono text-[22px] font-semibold tracking-[-0.035em] text-[var(--paper)]">{value}</p><p className="mt-1 text-[11px] text-[var(--paper-faint)]">{label}</p></>;
  return href ? <Link href={href} className="panel block rounded-xl p-4 transition-colors hover:border-[var(--line-strong)]">{content}</Link> : <div className="panel rounded-xl p-4">{content}</div>;
}

function Outcome({ label, value, color }: { label: string; value: number; color: string }) {
  return <div className="bg-[var(--ink-800)] px-5 py-4"><div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--paper-faint)]"><span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} /> {label}</div><p className="number-tabular font-mono text-2xl font-semibold tracking-[-0.04em] text-[var(--paper)]">{value}</p></div>;
}
