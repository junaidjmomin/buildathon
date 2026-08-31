"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CircleDollarSign,
  Clock3,
  DatabaseZap,
  Download,
  FileWarning,
  Fingerprint,
  LoaderCircle,
  Play,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { EmptyState, PageSkeleton } from "@/components/ui/primitives";
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
  const activeRunRecord = resolveActiveRun(runs.data, selectedRunId, { allowSeeded: isOverride });
  const activeRun = activeRunRecord?.id;
  const activeIsSeeded = activeRunRecord?.source_type === "DEMO";
  const exportEvidence = useMutation({ mutationFn: () => api.exportEvidence(activeRun ?? "") });
  const summary = useQuery({
    queryKey: ["run-summary", activeRun],
    queryFn: () => api.summary(activeRun ?? ""),
    enabled: Boolean(activeRun),
    placeholderData: (previous) => previous,
  });
  const violations = useQuery({
    queryKey: ["violations", activeRun],
    queryFn: () => api.violations(activeRun ?? ""),
    enabled: Boolean(activeRun),
  });
  const roots = useQuery({
    queryKey: ["root-causes", activeRun],
    queryFn: () => api.rootCauses(activeRun ?? ""),
    enabled: Boolean(activeRun),
  });
  const coverage = useQuery({
    queryKey: ["control-coverage", activeRun],
    queryFn: () => api.controlCoverage(activeRun ?? ""),
    enabled: Boolean(activeRun),
    retry: 1,
  });

  if (runs.isPending) {
    return <main className="mx-auto max-w-[1400px] px-5 py-8 md:px-8 md:py-10"><PageSkeleton cards={4} rows={5} /></main>;
  }

  if (runs.isError) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <div className="panel rounded-xl p-8 text-center" role="alert">
          <FileWarning className="mx-auto mb-4 text-[var(--crimson)]" />
          <h1 className="text-xl font-semibold text-[var(--paper)]">Runs could not be loaded</h1>
          <p className="mt-2 text-sm text-[var(--paper-dim)]">Check the authenticated API connection, then try again.</p>
          <button className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[var(--ink-800)]" onClick={() => void runs.refetch()}>Retry</button>
        </div>
      </main>
    );
  }

  if (!activeRun) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <EmptyState
          title="Create your first control run"
          body="Connect Razorpay or upload a related source bundle. The resulting run will appear here with verified exposure, exceptions and root causes."
          action={<Link href="/data" className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[var(--ink-800)]">Open data sources <ArrowRight size={15} /></Link>}
        />
      </main>
    );
  }

  if (summary.isPending || violations.isPending || roots.isPending) {
    return <main className="mx-auto max-w-[1400px] px-5 py-8 md:px-8 md:py-10"><PageSkeleton cards={4} rows={5} /></main>;
  }

  if (summary.isError) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <div className="panel rounded-xl p-8 text-center" role="alert">
          <FileWarning className="mx-auto mb-4 text-[var(--crimson)]" />
          <h1 className="text-xl font-semibold text-[var(--paper)]">The run summary is unavailable</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--paper-dim)]">No missing financial value has been replaced with demo data.</p>
          <button onClick={() => void summary.refetch()} className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[var(--ink-800)]">Retry summary</button>
        </div>
      </main>
    );
  }

  if (violations.isError || roots.isError) {
    return (
      <main className="mx-auto max-w-4xl px-5 py-16 md:px-8">
        <div className="panel rounded-xl p-8 text-center" role="alert">
          <FileWarning className="mx-auto mb-4 text-[var(--crimson)]" />
          <h1 className="text-xl font-semibold text-[var(--paper)]">The evidence view is incomplete</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--paper-dim)]">At least one evidence section failed to load. Missing values have not been shown as zero.</p>
          <button onClick={() => void queryClient.invalidateQueries()} className="mt-5 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[var(--ink-800)]">Retry evidence</button>
        </div>
      </main>
    );
  }

  if (!summary.data) return null;
  const data = summary.data;
  const unresolvedEvaluations = data.unresolved_control_count ?? data.unresolved_count ?? 0;
  const coveragePercent = activeIsSeeded ? data.control_coverage : coverage.data?.coverage_percentage ?? null;
  const coverageLabel = activeIsSeeded ? "Control coverage" : "Structural coverage";
  const coverageValue = coveragePercent != null ? formatPercent(coveragePercent) : coverage.isError ? "Unavailable" : "Loading…";
  const rankedViolations = (violations.data ?? []).slice().sort((left, right) => compareDecimals(right.financial_impact, left.financial_impact));
  const rankedRoots = (roots.data ?? []).slice().sort((left, right) => compareDecimals(right.verified_impact, left.verified_impact));
  const featuredViolation = rankedViolations[0];
  const featuredRoot = rankedRoots[0];
  const rootMax = rankedRoots.reduce((maximum, root) => compareDecimals(root.verified_impact, maximum) > 0 ? root.verified_impact : maximum, "0");
  const hasExposure = compareDecimals(data.verified_leakage, "0") > 0;
  const outcomeTotal = Math.max(data.breakdown.passed + data.breakdown.violation + data.breakdown.warning + data.breakdown.unresolved, 1);
  const nextAction = getNextAction({ activeRun, featuredViolation, featuredRoot, unresolvedEvaluations });

  return (
    <main className="mx-auto max-w-[1400px] px-5 py-7 md:px-8 md:py-9">
      <header className="mb-6 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div className="min-w-0">
          <p className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--evergreen)]"><Check size={13} /> Run complete</p>
          <h1 className="truncate text-3xl font-semibold tracking-[-0.04em] text-[var(--paper)] md:text-[38px]">{data.name}</h1>
          <p className="mt-2 text-sm text-[var(--paper-dim)]">{data.event_count.toLocaleString("en-IN")} financial events evaluated against the active control versions.</p>
        </div>
        {activeIsSeeded ? (
          <button
            onClick={() => void load.refetch().then(() => queryClient.invalidateQueries({ queryKey: ["run-summary", activeRun] }))}
            disabled={load.isFetching}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-4 py-2.5 text-sm font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)] disabled:opacity-60"
          >
            {load.isFetching ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />}
            {load.isFetching ? "Running controls…" : "Run controls again"}
          </button>
        ) : (
          <Link href="/data" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-4 py-2.5 text-sm font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)]">Create another run <ArrowRight size={15} /></Link>
        )}
      </header>

      <section className="mb-5 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] xl:grid-cols-[1.25fr_0.75fr]" aria-labelledby="exposure-title">
        <div className="border-b border-[var(--line)] p-5 xl:border-b-0 xl:border-r md:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${hasExposure ? "text-[var(--crimson)]" : "text-[var(--evergreen)]"}`}>{hasExposure ? "Verified exposure" : "No verified leakage"}</p>
              <h2 id="exposure-title" className={`number-tabular mt-2 font-mono text-4xl font-semibold tracking-[-0.05em] md:text-5xl ${hasExposure ? "text-[var(--crimson)]" : "text-[var(--evergreen)]"}`}>{formatMoney(data.verified_leakage)}</h2>
              <p className="mt-3 max-w-xl text-xs leading-5 text-[var(--paper-dim)]">Only proven excess deductions are included. Ambiguous matches remain unresolved and do not inflate this figure.</p>
            </div>
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--ink-700)] text-[var(--paper-dim)]"><CircleDollarSign size={20} /></span>
          </div>
          <Link href="/exceptions" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)]">
            Review {rankedViolations.length.toLocaleString("en-IN")} {rankedViolations.length === 1 ? "exception" : "exceptions"} <ArrowRight size={13} />
          </Link>
        </div>
        <div className="grid sm:grid-cols-3 xl:grid-cols-1">
          <ExposureFact label="Control violations" value={data.breakdown.violation.toLocaleString("en-IN")} tone="violation" href="/exceptions" />
          <ExposureFact label="Unresolved evaluations" value={unresolvedEvaluations.toLocaleString("en-IN")} tone="warning" href="/exceptions" />
          <ExposureFact label="Cash delayed beyond SLA" value={formatMoney(data.cash_delayed, true)} />
        </div>
      </section>

      <section className="mb-5 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] sm:grid-cols-2 xl:grid-cols-4" aria-label="Run scope and quality">
        <RunMetric icon={DatabaseZap} label="Transactions" value={data.transaction_count.toLocaleString("en-IN")} href="/data" />
        <RunMetric icon={Fingerprint} label="Control evaluations" value={data.control_evaluation_count.toLocaleString("en-IN")} href="/controls" />
        <RunMetric icon={ShieldCheck} label={coverageLabel} value={coverageValue} href={`/runs/${activeRun}/coverage`} />
        <RunMetric icon={ScanSearch} label={data.ground_truth_available ? "Precision" : "Run type"} value={data.ground_truth_available ? formatPercent(data.precision) : "Live data"} />
      </section>

      <section className="mb-5 grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="flex flex-col justify-between gap-3 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-sm font-semibold text-[var(--paper)]">Control outcomes</h2>
              <p className="mt-0.5 text-xs text-[var(--paper-dim)]">{data.ground_truth_available ? "Scored against available payment-level labels." : "Live control results; precision is not scored without labels."}</p>
            </div>
            <span className="w-fit rounded-full border border-[var(--line-strong)] bg-[var(--ink-800)] px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.08em] text-[var(--paper-dim)]">{data.ground_truth_available ? "Ground truth scored" : "Live outcomes"}</span>
          </div>
          <div className="grid grid-cols-2 divide-x divide-y divide-[var(--line)] sm:grid-cols-4 sm:divide-y-0">
            <Outcome label="Passed" value={data.breakdown.passed} color="var(--evergreen)" />
            <Outcome label="Violation" value={data.breakdown.violation} color="var(--crimson)" />
            <Outcome label="Warning" value={data.breakdown.warning} color="var(--amber)" />
            <Outcome label="Unresolved" value={data.breakdown.unresolved} color="var(--paper-faint)" />
          </div>
          <div className="px-5 py-4">
            <div className="flex h-2 overflow-hidden rounded-full bg-[var(--ink-600)]" role="img" aria-label={`${data.breakdown.passed} passed, ${data.breakdown.violation} violations, ${data.breakdown.warning} warnings and ${data.breakdown.unresolved} unresolved`}>
              <div className="bg-[var(--evergreen)]" style={{ width: `${(data.breakdown.passed / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--crimson)]" style={{ width: `${(data.breakdown.violation / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--amber)]" style={{ width: `${(data.breakdown.warning / outcomeTotal) * 100}%` }} />
              <div className="bg-[var(--paper-faint)]" style={{ width: `${(data.breakdown.unresolved / outcomeTotal) * 100}%` }} />
            </div>
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[10px] text-[var(--paper-dim)]">
              <span className="inline-flex items-center gap-1.5"><Clock3 size={12} /> {formatDuration(data.processing_ms)} processing</span>
              <span className="number-tabular font-mono">{data.evaluations_per_second.toLocaleString("en-IN")} evaluations/sec</span>
              <span className="number-tabular font-mono">{data.unresolved_relationship_count.toLocaleString("en-IN")} unresolved relationships</span>
              <span>{data.ground_truth_available ? `${formatPercent(data.false_positive_rate)} false-positive rate` : data.metrics_note || "Quality scoring requires labeled ground truth."}</span>
            </div>
          </div>
        </div>

        <aside className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--evergreen)]">Next action</p>
            <h2 className="mt-1.5 text-base font-semibold text-[var(--paper)]">{nextAction.title}</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{nextAction.body}</p>
          </div>
          <div className="space-y-3 p-5">
            <Link href={nextAction.href} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)]">{nextAction.label} <ArrowRight size={13} /></Link>
            <Link
              href={`/runs/${activeRun}/replay`}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)]"
            >
              <Clock3 size={13} /> Replay controls
            </Link>
            <Link
              href={`/runs/${activeRun}/operations`}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)]"
            >
              <DatabaseZap size={13} /> Run operations
            </Link>
            <button
              type="button"
              onClick={() => exportEvidence.mutate()}
              disabled={exportEvidence.isPending}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)] disabled:opacity-60"
            >
              {exportEvidence.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Download size={13} />}
              {exportEvidence.isPending ? "Preparing evidence…" : "Export evidence pack"}
            </button>
            {exportEvidence.data ? <p role="status" className="break-all text-[10px] leading-4 text-[var(--evergreen)]">Stored privately as {exportEvidence.data.artifact_id}.</p> : null}
            {exportEvidence.isError ? <p role="alert" className="text-[10px] leading-4 text-[var(--crimson)]">Evidence export is unavailable until private storage is configured.</p> : null}
          </div>
        </aside>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
        <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5">
            <div><h2 className="text-sm font-semibold text-[var(--paper)]">Root-cause impact</h2><p className="mt-0.5 text-xs text-[var(--paper-dim)]">Ranked by verified exposure.</p></div>
            <Link href="/root-causes" className="shrink-0 text-xs font-semibold text-[var(--evergreen)] hover:underline">View all</Link>
          </div>
          {rankedRoots.length === 0 ? (
            <p className="px-5 py-8 text-sm text-[var(--paper-dim)]">No deterministic root-cause clusters were found.</p>
          ) : (
            <div className="divide-y divide-[var(--line)]">
              {rankedRoots.slice(0, 5).map((root) => (
                <Link href={`/root-causes/${root.id}`} key={root.id} className="group block px-5 py-3.5 hover:bg-[var(--ink-700)]">
                  <div className="mb-2 flex items-center justify-between gap-3 text-xs"><span className="truncate font-semibold text-[var(--paper)]">{root.title}</span><span className="number-tabular shrink-0 font-mono text-[var(--paper-dim)]">{formatMoney(root.verified_impact, true)}</span></div>
                  <div className="h-1 overflow-hidden rounded-full bg-[var(--ink-600)]"><div className="h-full rounded-full bg-[var(--crimson)]" style={{ width: `${Math.max(3, ratioPercent(root.verified_impact, rootMax))}%` }} /></div>
                  <p className="mt-2 text-[9px] text-[var(--paper-faint)]">{root.affected_count.toLocaleString("en-IN")} affected · {root.primary_violation_count.toLocaleString("en-IN")} primary</p>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="flex flex-col justify-between gap-2 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-3.5 sm:flex-row sm:items-center">
            <div><h2 className="text-sm font-semibold text-[var(--paper)]">Highest-impact exceptions</h2><p className="mt-0.5 text-xs text-[var(--paper-dim)]">Open the supporting proof or its root cause.</p></div>
            <Link href="/exceptions" className="shrink-0 text-xs font-semibold text-[var(--evergreen)] hover:underline">View all · {rankedViolations.length.toLocaleString("en-IN")}</Link>
          </div>
          {rankedViolations.length === 0 ? (
            <div className="flex items-center gap-2 px-5 py-8 text-sm text-[var(--paper-dim)]"><ShieldCheck size={16} className="text-[var(--evergreen)]" /> No verified exceptions were found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--paper-faint)]"><tr><th className="px-5 py-2.5">Payment</th><th className="px-3 py-2.5">Category</th><th className="px-3 py-2.5">Expected</th><th className="px-3 py-2.5">Actual</th><th className="px-3 py-2.5 text-right">Impact</th><th className="w-10"><span className="sr-only">Open</span></th></tr></thead>
                <tbody className="divide-y divide-[var(--line)]">
                  {rankedViolations.slice(0, 6).map((item) => {
                    const href = item.target_type === "PAYMENT"
                      ? `/runs/${activeRun}/payments/${item.payment_id}`
                      : item.root_cause_id
                        ? `/root-causes/${item.root_cause_id}`
                        : null;
                    return (
                      <tr key={item.id} className="group hover:bg-[var(--ink-700)]">
                        <td className="number-tabular px-5 py-3.5 font-mono text-[11px] font-semibold text-[var(--evergreen)]">{item.payment_id}</td>
                        <td className="px-3 py-3.5 font-medium text-[var(--paper)]">{item.category}</td>
                        <td className="px-3 py-3.5 text-[var(--paper-dim)]">{item.expected}</td>
                        <td className="px-3 py-3.5 text-[var(--crimson)]">{item.actual}</td>
                        <td className="number-tabular px-3 py-3.5 text-right font-mono font-semibold text-[var(--paper)]">{formatMoney(item.financial_impact)}</td>
                        <td className="px-3">{href ? <Link href={href} aria-label={`Open evidence for ${item.payment_id}`}><ArrowRight size={15} className="text-[var(--paper-faint)] group-hover:text-[var(--evergreen)]" /></Link> : null}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function getNextAction({
  activeRun,
  featuredViolation,
  featuredRoot,
  unresolvedEvaluations,
}: {
  activeRun: string;
  featuredViolation: Awaited<ReturnType<typeof api.violations>>[number] | undefined;
  featuredRoot: Awaited<ReturnType<typeof api.rootCauses>>[number] | undefined;
  unresolvedEvaluations: number;
}) {
  if (featuredViolation?.target_type === "PAYMENT") {
    return {
      title: `Inspect ${featuredViolation.payment_id}`,
      body: "Start with the highest-impact payment and confirm its complete financial proof.",
      href: `/runs/${activeRun}/payments/${featuredViolation.payment_id}`,
      label: "Open payment proof",
    };
  }
  if (featuredRoot) {
    return {
      title: featuredRoot.title,
      body: "Review the leading root cause, affected payments and causal evidence before taking action.",
      href: `/root-causes/${featuredRoot.id}`,
      label: "Investigate root cause",
    };
  }
  if (unresolvedEvaluations > 0) {
    return {
      title: "Review unresolved evidence",
      body: "Resolve ambiguous relationships before treating this run as complete.",
      href: "/exceptions",
      label: "Open unresolved queue",
    };
  }
  return {
    title: "Validate control coverage",
    body: "Review governed relationships and blind spots before closing the run.",
    href: `/runs/${activeRun}/coverage`,
    label: "Review coverage",
  };
}

function formatDuration(milliseconds: number): string {
  if (milliseconds >= 1000) return `${(milliseconds / 1000).toFixed(milliseconds >= 10_000 ? 1 : 2)} s`;
  return `${milliseconds} ms`;
}

function ExposureFact({ label, value, tone = "default", href }: { label: string; value: string; tone?: "default" | "violation" | "warning"; href?: string }) {
  const valueClass = tone === "violation" ? "text-[var(--crimson)]" : tone === "warning" ? "text-[var(--amber)]" : "text-[var(--paper)]";
  const content = <><p className={`number-tabular font-mono text-lg font-semibold tracking-[-0.03em] ${valueClass}`}>{value}</p><p className="mt-1 text-[10px] font-medium uppercase tracking-[0.09em] text-[var(--paper-faint)]">{label}</p></>;
  return href ? <Link href={href} className="border-b border-[var(--line)] px-5 py-4 last:border-b-0 hover:bg-[var(--ink-700)] sm:border-b-0 sm:border-r sm:last:border-r-0 xl:border-b xl:border-r-0 xl:last:border-b-0">{content}</Link> : <div className="border-b border-[var(--line)] px-5 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0 xl:border-b xl:border-r-0 xl:last:border-b-0">{content}</div>;
}

function RunMetric({ icon: Icon, label, value, href }: { icon: typeof DatabaseZap; label: string; value: string; href?: string }) {
  const content = <div className="flex items-center gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--ink-700)] text-[var(--evergreen)]"><Icon size={15} /></span><div className="min-w-0"><p className="number-tabular truncate font-mono text-lg font-semibold tracking-[-0.03em] text-[var(--paper)]">{value}</p><p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.09em] text-[var(--paper-faint)]">{label}</p></div></div>;
  const className = "border-b border-[var(--line)] px-4 py-3.5 last:border-b-0 sm:border-b-0 sm:border-r sm:[&:nth-child(2)]:border-r-0 xl:[&:nth-child(2)]:border-r xl:last:border-r-0";
  return href ? <Link href={href} className={`${className} hover:bg-[var(--ink-700)]`}>{content}</Link> : <div className={className}>{content}</div>;
}

function Outcome({ label, value, color }: { label: string; value: number; color: string }) {
  return <div className="px-5 py-4"><div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]"><span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} /> {label}</div><p className="number-tabular font-mono text-xl font-semibold tracking-[-0.04em] text-[var(--paper)]">{value.toLocaleString("en-IN")}</p></div>;
}
