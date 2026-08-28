"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, Banknote, Check, CircleAlert, FileText, GitBranch, LoaderCircle, Scale } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, MoneyText } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { compareDecimals, formatMoney } from "@/lib/format";
import type { EvaluationStatus } from "@/types/api";

export default function PaymentPage() {
  const params = useParams<{ runId: string; paymentId: string }>();
  const payment = useQuery({
    queryKey: ["payment", params.runId, params.paymentId],
    queryFn: () => api.expectedActual(params.runId, params.paymentId),
  });
  const graph = useQuery({
    queryKey: ["payment-graph", params.runId, params.paymentId],
    queryFn: () => api.paymentGraph(params.runId, params.paymentId),
  });
  const lineage = useQuery({
    queryKey: ["lineage", params.runId, params.paymentId],
    queryFn: () => api.lineage(params.runId, params.paymentId),
  });
  const counterfactual = useQuery({
    queryKey: ["counterfactual", params.runId, params.paymentId],
    queryFn: () => api.counterfactual(params.runId, params.paymentId),
  });

  if (payment.isPending) return <div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[var(--evergreen)]" /></div>;
  if (!payment.data || payment.isError) return <main className="mx-auto max-w-3xl px-5 py-10 md:px-8"><ErrorState what="Payment evidence" onRetry={() => payment.refetch()} /></main>;
  const data = payment.data;
  const isUnresolved = data.status === "UNRESOLVED";
  const traditionalMatch = data.bank_credit !== null && data.gateway_net === data.bank_credit;

  return (
    <main className="mx-auto max-w-[1240px] px-5 py-7 md:px-8 md:py-9">
      <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[var(--paper-dim)] transition-colors duration-150 hover:text-[var(--paper)]"><ArrowLeft size={14} /> Back to control run</Link>
      <section className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2"><Badge status={data.status === "VIOLATION" ? "VIOLATION" : isUnresolved ? "UNRESOLVED" : "PASS"} label={data.status === "VIOLATION" ? "CONTROL VIOLATION" : data.status} /><span className="text-xs text-[var(--paper-dim)]">{isUnresolved ? "Evidence boundary preserved" : "100% evidence confidence"}</span></div>
          <h1 className="font-mono text-3xl font-semibold tracking-[-0.04em] text-[var(--paper)]">{data.payment_id}</h1>
          <p className="mt-2 text-sm text-[var(--paper-dim)]">{data.descriptor} · <MoneyText className="text-sm" amount={formatMoney(data.amount)} /></p>
        </div>
        <div className="rounded-xl border border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)] px-5 py-3.5 text-right"><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--crimson)]">Verified leakage</p><MoneyText className="mt-1 text-2xl tracking-[-0.04em]" amount={formatMoney(data.verified_leakage)} tone="violation" /></div>
      </section>

      <section className="mb-6 grid gap-4 md:grid-cols-2">
        <Comparison label="Traditional reconciliation" icon={Banknote} rows={[["Gateway net", formatMoney(data.gateway_net)], ["Bank credit", formatMoney(data.bank_credit)]]} result={traditionalMatch ? "MATCH" : "UNRESOLVED"} pass={traditionalMatch} />
        <Comparison label="sl3dge control verification" icon={Scale} rows={[["Expected net", formatMoney(data.expected_net)], ["Actual net", formatMoney(data.gateway_net)]]} result={data.status} pass={data.status === "PASS"} />
      </section>

      <section className="panel mb-6 overflow-hidden rounded-2xl">
        <div className="flex flex-col justify-between gap-3 border-b border-[var(--line)] px-5 py-4 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold text-[var(--paper)]">Expected vs actual</h2><p className="mt-1 text-xs text-[var(--paper-dim)]">Expected state is calculated independently from the settlement record.</p></div><div className="text-left sm:text-right"><Badge status="PASS" label="DECIMAL VERIFIED" /><p className="number-tabular mt-2 font-mono text-[9px] text-[var(--paper-faint)]">{data.applied_control_id} · v{data.applied_control_version} · {data.applied_control_effective_period}</p></div></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left">
            <thead className="bg-[var(--ink-700)] text-[10px] uppercase tracking-[0.12em] text-[var(--paper-faint)]"><tr><th className="px-5 py-3">Cash component</th><th className="px-4 py-3 text-right">Expected</th><th className="px-4 py-3 text-right">Actual</th><th className="px-5 py-3 text-right">Status</th></tr></thead>
            <tbody className="divide-y divide-[var(--line)]">
              {data.rows.map((row) => (
                <tr key={row.label} className={row.status === "VIOLATION" ? "bg-[rgba(226,96,79,0.06)]" : ""}>
                  <td className="px-5 py-4 text-sm font-medium text-[var(--paper)]">{row.label}</td><td className="number-tabular px-4 py-4 text-right font-mono text-sm text-[var(--paper-dim)]">{formatMoney(row.expected)}</td><td className={`number-tabular px-4 py-4 text-right font-mono text-sm ${row.status === "VIOLATION" ? "font-semibold text-[var(--crimson)]" : "text-[var(--paper)]"}`}>{formatMoney(row.actual)}</td><td className="px-5 py-4 text-right"><StatusBadge status={row.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {counterfactual.data && lineage.data && <section className="mb-6 grid gap-5 lg:grid-cols-2">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4"><h2 className="text-sm font-semibold text-[var(--paper)]">Counterfactual settlement</h2><p className="mt-1 text-xs text-[var(--paper-dim)]">Actual cash flow vs verified correct cash flow</p></div>
          <div className="p-5">
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-5 gap-y-3 text-xs"><span /><strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Actual</strong><strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[var(--evergreen)]">Correct</strong>
              {(["gross", "mdr", "gst", "refunds", "net"] as const).map((key) => <div className="contents" key={key}><span className={key === "net" ? "number-tabular border-t border-[var(--line-strong)] pt-3 font-mono font-semibold capitalize text-[var(--paper)]" : "capitalize text-[var(--paper-dim)]"}>{key}</span><span className={`number-tabular text-right font-mono ${key === "net" ? "border-t border-[var(--line-strong)] pt-3 font-semibold text-[var(--paper)]" : "text-[var(--paper-dim)]"}`}>{formatMoney(counterfactual.data.actual[key])}</span><span className={`number-tabular text-right font-mono ${key === "net" ? "border-t border-[var(--line-strong)] pt-3 font-semibold text-[var(--evergreen)]" : "text-[var(--paper-dim)]"}`}>{formatMoney(counterfactual.data.expected[key])}</span></div>)}
            </div>
            <div className="mt-5 rounded-xl border border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)] p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--crimson)]">Correct settlement should be</p><div className="mt-1 flex items-end justify-between"><MoneyText className="text-xl" amount={formatMoney(counterfactual.data.expected.net)} tone="violation" /><span className="number-tabular font-mono text-xs font-semibold text-[var(--crimson)]">+{formatMoney(counterfactual.data.difference)}</span></div><div className="mt-3 flex flex-wrap gap-2">{counterfactual.data.drivers.map((driver) => <span key={driver.type} className="number-tabular rounded-full border border-[var(--line)] bg-[var(--ink-700)] px-2.5 py-1 font-mono text-[10px] text-[var(--paper-dim)]">{formatMoney(driver.amount)} {driver.type.replaceAll("_", " ").toLowerCase()}</span>)}</div></div>
          </div>
        </div>
        <div className="panel overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4"><div><h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]"><GitBranch size={15} className="text-[var(--evergreen)]" /> Violation lineage</h2><p className="mt-1 text-xs text-[var(--paper-dim)]">One cause, not four independent problems</p></div><span className="number-tabular font-mono text-[10px] text-[var(--paper-faint)]">{lineage.data.primary_violation_count} primary · {lineage.data.downstream_effect_count} downstream</span></div>
          <div className="p-5">{lineage.data.nodes.map((node, index) => <div key={node.id}><div className={`rounded-xl border p-3 ${node.lineage_type === "PRIMARY" ? "border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)]" : "border-[var(--line)] bg-[var(--ink-700)]"}`}><div className="flex items-center justify-between gap-3"><div><span className={`text-[9px] font-bold uppercase tracking-[0.12em] ${node.lineage_type === "PRIMARY" ? "text-[var(--crimson)]" : "text-[var(--paper-faint)]"}`}>{node.lineage_type}</span><p className="mt-0.5 text-xs font-semibold text-[var(--paper)]">{node.category}</p></div><span className="number-tabular font-mono text-xs font-semibold text-[var(--paper)]">{formatMoney(node.difference)}</span></div><p className="mt-2 text-[10px] leading-4 text-[var(--paper-dim)]">{typeof node.causal_evidence === "string" ? node.causal_evidence : JSON.stringify(node.causal_evidence)}</p></div>{index < lineage.data.nodes.length - 1 && <ArrowDown size={13} className="mx-auto my-1 text-[var(--paper-faint)]" />}</div>)}</div>
        </div>
      </section>}

      <section className="grid gap-5 lg:grid-cols-2">
        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--paper)]"><FileText size={16} className="text-[var(--evergreen)]" /> Why this failed</div>
          <div className="space-y-3">
            {data.evidence.map((evidence) => (
              <div key={evidence.control} className="panel rounded-xl p-4">
                <div className="mb-3 flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-[var(--paper)]">{evidence.title}</p><p className="mt-1 font-mono text-[10px] text-[var(--paper-faint)]">{evidence.control}</p></div>{evidence.difference !== null && compareDecimals(evidence.difference, "0") > 0 ? <CircleAlert size={17} className="text-[var(--crimson)]" /> : <Check size={17} className="text-[var(--evergreen)]" />}</div>
                <div className="number-tabular rounded-lg border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 font-mono text-xs font-medium text-[var(--paper-dim)]">{evidence.calculation}</div>
                <div className="mt-3 grid grid-cols-3 gap-3 text-xs"><div><span className="block text-[10px] text-[var(--paper-faint)]">Expected</span><strong className="number-tabular font-mono text-[var(--paper)]">{formatMoney(evidence.expected)}</strong></div><div><span className="block text-[10px] text-[var(--paper-faint)]">Actual</span><strong className="number-tabular font-mono text-[var(--paper)]">{formatMoney(evidence.actual)}</strong></div><div><span className="block text-[10px] text-[var(--paper-faint)]">Difference</span><strong className="number-tabular font-mono text-[var(--crimson)]">{formatMoney(evidence.difference)}</strong></div></div>
                <div className="mt-4 border-t border-[var(--line)] pt-3 text-[11px] text-[var(--paper-dim)]">{evidence.source} · <span className="font-medium text-[var(--evergreen)]">{evidence.source_clause}</span><div className="mt-2 flex flex-wrap gap-2 font-mono text-[9px] text-[var(--paper-faint)]">{evidence.control_version ? <span>control v{evidence.control_version}</span> : null}{evidence.evaluation_id ? <span>eval {evidence.evaluation_id}</span> : null}{evidence.source_snapshot_ids?.length ? <span>{evidence.source_snapshot_ids.length} source snapshot{evidence.source_snapshot_ids.length === 1 ? "" : "s"}</span> : null}</div></div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-3 text-sm font-semibold text-[var(--paper)]">Trace money</div>
          <div className="panel rounded-xl p-4">
            {graph.isPending ? <div className="grid h-64 place-items-center"><LoaderCircle className="animate-spin text-[var(--evergreen)]" /></div> : (
              <div className="space-y-2">
                {graph.data?.nodes.map((node, index) => <div key={`${node.id}-${index}`}>
                  <div className={`flex items-center justify-between rounded-xl border p-3 ${node.status === "VIOLATION" ? "border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)]" : "border-[var(--line)] bg-[var(--ink-700)]"}`}>
                    <div className="flex items-center gap-3"><span className={`grid h-8 w-8 place-items-center rounded-lg text-[9px] font-bold ${node.status === "VIOLATION" ? "bg-[rgba(226,96,79,0.2)] text-[var(--crimson)]" : "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]"}`}>{node.kind.slice(0, 3)}</span><div><p className="text-xs font-semibold text-[var(--paper)]">{node.label}</p><p className="font-mono text-[9px] text-[var(--paper-faint)]">{node.id}</p></div></div>
                    <div className="text-right"><p className="number-tabular font-mono text-xs font-semibold text-[var(--paper)]">{formatMoney(node.amount)}</p>{node.detail && <p className="mt-0.5 text-[9px] text-[var(--crimson)]">{node.detail}</p>}</div>
                  </div>
                  {index < (graph.data?.nodes.length ?? 0) - 1 && <div className="ml-7 h-2.5 border-l border-dashed border-[var(--line-strong)]" />}
                </div>)}
              </div>
            )}
            <p className="mt-4 border-t border-[var(--line)] pt-3 text-[10px] leading-4 text-[var(--paper-dim)]">Relationships are exact-ID or typed-rule matches. No ambiguous link is forced into this lifecycle.</p>
          </div>
        </div>
      </section>
    </main>
  );
}

function Comparison({ label, icon: Icon, rows, result, pass = false }: { label: string; icon: typeof Banknote; rows: [string, string][]; result: string; pass?: boolean }) {
  const unresolved = result === "UNRESOLVED";
  return <div className={`rounded-2xl border p-5 ${pass ? "border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.1)]" : unresolved ? "border-[var(--line)] bg-[var(--ink-800)]" : "border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.1)]"}`}><div className="mb-5 flex items-center justify-between"><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.09em] text-[var(--paper)]"><Icon size={15} /> {label}</div><Badge status={pass ? "PASS" : unresolved ? "UNRESOLVED" : "VIOLATION"} label={result} /></div><div className="space-y-2">{rows.map(([name, value]) => <div key={name} className="flex justify-between text-sm"><span className="text-[var(--paper-dim)]">{name}</span><strong className="number-tabular font-mono text-[var(--paper)]">{value}</strong></div>)}</div></div>;
}

function StatusBadge({ status }: { status: EvaluationStatus }) {
  return <span className="ml-auto flex w-fit justify-end"><Badge status={status === "PASS" ? "PASS" : status === "UNRESOLVED" ? "UNRESOLVED" : status === "WARNING" ? "PENDING" : "VIOLATION"} label={status} /></span>;
}
