"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, Banknote, Check, CircleAlert, FileText, GitBranch, LoaderCircle, Scale, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
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

  if (payment.isPending) return <AppShell><div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[#1e6b51]" /></div></AppShell>;
  if (!payment.data || payment.isError) return <AppShell><main className="p-8">Payment evidence could not be loaded.</main></AppShell>;
  const data = payment.data;
  const isUnresolved = data.status === "UNRESOLVED";
  const traditionalMatch = data.bank_credit !== null && data.gateway_net === data.bank_credit;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 md:px-8 md:py-9">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[#5e6a64] hover:text-[#1e6b51]"><ArrowLeft size={14} /> Back to control run</Link>
        <section className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2"><span className={`rounded-md px-2 py-1 text-[10px] font-bold tracking-[0.1em] ${isUnresolved ? "bg-[#eceeed] text-[#5d6862]" : "bg-[#ffe5d8] text-[#c65024]"}`}>{data.status === "VIOLATION" ? "CONTROL VIOLATION" : data.status}</span><span className="text-xs text-[#6f7a74]">{isUnresolved ? "Evidence boundary preserved" : "100% evidence confidence"}</span></div>
            <h1 className="font-mono text-3xl font-semibold tracking-[-0.04em]">{data.payment_id}</h1>
            <p className="mt-2 text-sm text-[#66716b]">{data.descriptor} · {formatMoney(data.amount)}</p>
          </div>
          <div className="rounded-xl border border-[#efc6b3] bg-[#fff5ef] px-5 py-3.5 text-right"><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#bb542e]">Verified leakage</p><p className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-[#a9431f]">{formatMoney(data.verified_leakage)}</p></div>
        </section>

        <section className="mb-6 grid gap-4 md:grid-cols-2">
          <Comparison label="Traditional reconciliation" icon={Banknote} rows={[["Gateway net", formatMoney(data.gateway_net)], ["Bank credit", formatMoney(data.bank_credit)]]} result={traditionalMatch ? "MATCH" : "UNRESOLVED"} pass={traditionalMatch} />
          <Comparison label="sl3dge control verification" icon={Scale} rows={[["Expected net", formatMoney(data.expected_net)], ["Actual net", formatMoney(data.gateway_net)]]} result={data.status} pass={data.status === "PASS"} />
        </section>

        <section className="panel mb-6 overflow-hidden rounded-2xl">
          <div className="flex flex-col justify-between gap-3 border-b border-[#e2e5df] px-5 py-4 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold">Expected vs actual</h2><p className="mt-1 text-xs text-[#78827d]">Expected state is calculated independently from the settlement record.</p></div><div className="text-left sm:text-right"><span className="rounded-full bg-[#dff2e8] px-2.5 py-1 text-[10px] font-semibold text-[#1e6b51]">DECIMAL VERIFIED</span><p className="mt-2 font-mono text-[9px] text-[#68736d]">{data.applied_control_id} · v{data.applied_control_version} · {data.applied_control_effective_period}</p></div></div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left">
              <thead className="bg-[#f8f9f6] text-[10px] uppercase tracking-[0.12em] text-[#78827d]"><tr><th className="px-5 py-3">Cash component</th><th className="px-4 py-3 text-right">Expected</th><th className="px-4 py-3 text-right">Actual</th><th className="px-5 py-3 text-right">Status</th></tr></thead>
              <tbody className="divide-y divide-[#e9ece7]">
                {data.rows.map((row) => (
                  <tr key={row.label} className={row.status === "VIOLATION" ? "bg-[#fffaf7]" : ""}>
                    <td className="px-5 py-4 text-sm font-medium">{row.label}</td><td className="number-tabular px-4 py-4 text-right text-sm">{formatMoney(row.expected)}</td><td className={`number-tabular px-4 py-4 text-right text-sm ${row.status === "VIOLATION" ? "font-semibold text-[#b24a24]" : ""}`}>{formatMoney(row.actual)}</td><td className="px-5 py-4"><StatusBadge status={row.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {counterfactual.data && lineage.data && <section className="mb-6 grid gap-5 lg:grid-cols-2">
          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Counterfactual settlement</h2><p className="mt-1 text-xs text-[#78827d]">Actual cash flow vs verified correct cash flow</p></div>
            <div className="p-5">
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-5 gap-y-3 text-xs"><span /><strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[#7a847e]">Actual</strong><strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[#1e6b51]">Correct</strong>
                {(["gross", "mdr", "gst", "refunds", "net"] as const).map((key) => <div className="contents" key={key}><span className={key === "net" ? "border-t border-[#dfe3dc] pt-3 font-semibold capitalize" : "capitalize text-[#66716b]"}>{key}</span><span className={`number-tabular text-right ${key === "net" ? "border-t border-[#dfe3dc] pt-3 font-semibold" : ""}`}>{formatMoney(counterfactual.data.actual[key])}</span><span className={`number-tabular text-right ${key === "net" ? "border-t border-[#dfe3dc] pt-3 font-semibold text-[#1e6b51]" : ""}`}>{formatMoney(counterfactual.data.expected[key])}</span></div>)}
              </div>
              <div className="mt-5 rounded-xl bg-[#fff0e8] p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#bd522a]">Correct settlement should be</p><div className="mt-1 flex items-end justify-between"><strong className="text-xl text-[#a9431f]">{formatMoney(counterfactual.data.expected.net)}</strong><span className="text-xs font-semibold text-[#bd522a]">+{formatMoney(counterfactual.data.difference)}</span></div><div className="mt-3 flex flex-wrap gap-2">{counterfactual.data.drivers.map((driver) => <span key={driver.type} className="rounded-full bg-white/80 px-2.5 py-1 text-[10px] text-[#82513e]">{formatMoney(driver.amount)} {driver.type.replaceAll("_", " ").toLowerCase()}</span>)}</div></div>
            </div>
          </div>
          <div className="panel overflow-hidden rounded-2xl">
            <div className="flex items-center justify-between border-b border-[#e2e5df] px-5 py-4"><div><h2 className="flex items-center gap-2 text-sm font-semibold"><GitBranch size={15} className="text-[#1e6b51]" /> Violation lineage</h2><p className="mt-1 text-xs text-[#78827d]">One cause, not four independent problems</p></div><span className="text-[10px] text-[#68736d]">{lineage.data.primary_violation_count} primary · {lineage.data.downstream_effect_count} downstream</span></div>
            <div className="p-5">{lineage.data.nodes.map((node, index) => <div key={node.id}><div className={`rounded-xl border p-3 ${node.lineage_type === "PRIMARY" ? "border-[#efc6b3] bg-[#fff7f2]" : "border-[#dde3dd] bg-[#f8faf7]"}`}><div className="flex items-center justify-between gap-3"><div><span className={`text-[9px] font-bold uppercase tracking-[0.12em] ${node.lineage_type === "PRIMARY" ? "text-[#bd4e25]" : "text-[#65716b]"}`}>{node.lineage_type}</span><p className="mt-0.5 text-xs font-semibold">{node.category}</p></div><span className="number-tabular text-xs font-semibold">{formatMoney(node.difference)}</span></div><p className="mt-2 text-[10px] leading-4 text-[#6c7771]">{node.causal_evidence}</p></div>{index < lineage.data.nodes.length - 1 && <ArrowDown size={13} className="mx-auto my-1 text-[#87928b]" />}</div>)}</div>
          </div>
        </section>}

        <section className="grid gap-5 lg:grid-cols-2">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><FileText size={16} className="text-[#1e6b51]" /> Why this failed</div>
            <div className="space-y-3">
              {data.evidence.map((evidence) => (
                <div key={evidence.control} className="panel rounded-xl p-4">
                  <div className="mb-3 flex items-start justify-between gap-3"><div><p className="text-xs font-semibold">{evidence.title}</p><p className="mt-1 font-mono text-[10px] text-[#7a847e]">{evidence.control}</p></div>{Number(evidence.difference) > 0 ? <CircleAlert size={17} className="text-[#e86f3a]" /> : <Check size={17} className="text-[#2a8a60]" />}</div>
                  <div className="rounded-lg bg-[#f4f6f1] px-3 py-2.5 font-mono text-xs font-medium">{evidence.calculation}</div>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-xs"><div><span className="block text-[10px] text-[#7a847e]">Expected</span><strong>{formatMoney(evidence.expected)}</strong></div><div><span className="block text-[10px] text-[#7a847e]">Actual</span><strong>{formatMoney(evidence.actual)}</strong></div><div><span className="block text-[10px] text-[#7a847e]">Difference</span><strong className="text-[#b14e29]">{formatMoney(evidence.difference)}</strong></div></div>
                  <div className="mt-4 border-t border-[#e5e8e2] pt-3 text-[11px] text-[#69736e]">{evidence.source} · <span className="font-medium text-[#1e6b51]">{evidence.source_clause}</span></div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-3 text-sm font-semibold">Trace money</div>
            <div className="panel rounded-xl p-4">
              {graph.isPending ? <div className="grid h-64 place-items-center"><LoaderCircle className="animate-spin text-[#1e6b51]" /></div> : (
                <div className="space-y-2">
                  {graph.data?.nodes.map((node, index) => <div key={`${node.id}-${index}`}>
                    <div className={`flex items-center justify-between rounded-xl border p-3 ${node.status === "VIOLATION" ? "border-[#efc6b3] bg-[#fff7f2]" : "border-[#e1e5de] bg-white"}`}>
                      <div className="flex items-center gap-3"><span className={`grid h-8 w-8 place-items-center rounded-lg text-[9px] font-bold ${node.status === "VIOLATION" ? "bg-[#ffe3d4] text-[#ba4c25]" : "bg-[#e8f3ed] text-[#1e6b51]"}`}>{node.kind.slice(0, 3)}</span><div><p className="text-xs font-semibold">{node.label}</p><p className="font-mono text-[9px] text-[#7b857f]">{node.id}</p></div></div>
                      <div className="text-right"><p className="number-tabular text-xs font-semibold">{formatMoney(node.amount)}</p>{node.detail && <p className="mt-0.5 text-[9px] text-[#bd542e]">{node.detail}</p>}</div>
                    </div>
                    {index < (graph.data?.nodes.length ?? 0) - 1 && <div className="ml-7 h-2.5 border-l border-dashed border-[#aeb8b2]" />}
                  </div>)}
                </div>
              )}
              <p className="mt-4 border-t border-[#e5e8e2] pt-3 text-[10px] leading-4 text-[#748079]">Relationships are exact-ID or typed-rule matches. No ambiguous link is forced into this lifecycle.</p>
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

function Comparison({ label, icon: Icon, rows, result, pass = false }: { label: string; icon: typeof Banknote; rows: [string, string][]; result: string; pass?: boolean }) {
  const unresolved = result === "UNRESOLVED";
  return <div className={`rounded-2xl border p-5 ${pass ? "border-[#cce2d5] bg-[#f5fbf7]" : unresolved ? "border-[#d9ded9] bg-[#f7f8f5]" : "border-[#efc6b3] bg-[#fff7f2]"}`}><div className="mb-5 flex items-center justify-between"><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.09em]"><Icon size={15} /> {label}</div><span className={`flex items-center gap-1 rounded-full px-2 py-1 text-[9px] font-bold ${pass ? "bg-[#dff2e8] text-[#1e6b51]" : unresolved ? "bg-[#e5e8e5] text-[#5f6a64]" : "bg-[#ffe2d2] text-[#b54822]"}`}>{pass ? <Check size={10} /> : unresolved ? <CircleAlert size={10} /> : <X size={10} />}{result}</span></div><div className="space-y-2">{rows.map(([name, value]) => <div key={name} className="flex justify-between text-sm"><span className="text-[#66716b]">{name}</span><strong className="number-tabular">{value}</strong></div>)}</div></div>;
}

function StatusBadge({ status }: { status: EvaluationStatus }) {
  const pass = status === "PASS"; const unresolved = status === "UNRESOLVED";
  return <span className={`ml-auto flex w-fit items-center gap-1.5 rounded-full px-2 py-1 text-[9px] font-bold ${pass ? "bg-[#e4f3eb] text-[#1e6b51]" : unresolved ? "bg-[#eceeed] text-[#65706a]" : "bg-[#ffe4d6] text-[#bb4b23]"}`}>{pass ? <Check size={10} /> : unresolved ? <CircleAlert size={10} /> : <X size={10} />}{status}</span>;
}
