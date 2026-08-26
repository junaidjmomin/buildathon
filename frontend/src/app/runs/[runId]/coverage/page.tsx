"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, CircleAlert, GitBranch, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

export default function ControlCoveragePage() {
  const { runId } = useParams<{ runId: string }>();
  const coverage = useQuery({
    queryKey: ["control-coverage", runId],
    queryFn: () => api.controlCoverage(runId),
  });

  if (coverage.isPending) return <AppShell><div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[#1e6b51]" /></div></AppShell>;
  if (!coverage.data) return <AppShell><main className="p-8">Control coverage could not be loaded.</main></AppShell>;
  const data = coverage.data;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-8 md:px-8 md:py-10">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[#5e6a64]"><ArrowLeft size={14} /> Back to control run</Link>
        <section className="mb-7"><p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><GitBranch size={14} /> Control coverage graph</p><h1 className="text-3xl font-semibold tracking-[-0.035em]">Which money relationships are governed?</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#66716b]">Every material event edge is mapped to an approved control—or exposed as a measurable blind spot.</p></section>

        <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Material edges" value={data.total_material_edges.toLocaleString("en-IN")} />
          <Metric label="Governed" value={data.governed_edges.toLocaleString("en-IN")} tone="green" />
          <Metric label="Ungoverned" value={data.ungoverned_edges.toLocaleString("en-IN")} tone="orange" />
          <Metric label="Control coverage" value={formatPercent(data.coverage_percentage, 2)} tone="green" />
        </section>

        <section className="panel mb-6 overflow-hidden rounded-2xl">
          <div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Material relationship coverage</h2><p className="mt-1 text-xs text-[#78827d]">Aggregate edge counts calculated from the canonical event lifecycle</p></div>
          <div className="divide-y divide-[#e8ebe6]">{data.items.map((item) => {
            const rate = item.material_edge_count ? (item.governed_edge_count / item.material_edge_count) * 100 : 100;
            const governed = item.status === "GOVERNED";
            return <div key={item.id} className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><div className="flex items-center gap-2"><span className={`grid h-7 w-7 place-items-center rounded-lg ${governed ? "bg-[#dff2e8] text-[#1e6b51]" : "bg-[#ffe5d8] text-[#bd4e24]"}`}>{governed ? <Check size={13} /> : <CircleAlert size={13} />}</span><h3 className="font-mono text-xs font-semibold">{item.relationship}</h3></div><p className="ml-9 mt-1 text-xs text-[#6d7872]">{item.description}</p></div><div className="text-left sm:text-right"><span className={`rounded-full px-2 py-1 text-[9px] font-bold ${governed ? "bg-[#e5f3eb] text-[#1e6b51]" : "bg-[#fff0e8] text-[#bd4e24]"}`}>{item.status}</span><p className="mt-2 text-[10px] text-[#78827d]">{item.governed_edge_count}/{item.material_edge_count} edges</p></div></div><div className="ml-9 mt-3 h-1.5 overflow-hidden rounded-full bg-[#edf0eb]"><div className={`h-full rounded-full ${governed ? "bg-[#2d7a5d]" : "bg-[#e86f3a]"}`} style={{ width: `${Math.max(rate, item.material_edge_count ? 1 : 100)}%` }} /></div><div className="ml-9 mt-3 flex flex-wrap gap-2">{item.control_ids.map((control) => <span key={control} className="rounded-md bg-[#eef2ed] px-2 py-1 font-mono text-[9px] text-[#52615a]">{control}</span>)}{item.blind_spot && <p className="w-full text-[10px] leading-5 text-[#a34a2a]">{item.blind_spot}</p>}</div></div>;
          })}</div>
        </section>

        <Link href={`/runs/${runId}/mutation-test`} className="flex flex-col justify-between gap-4 rounded-2xl border border-[#cbded3] bg-[#f4fbf7] p-5 sm:flex-row sm:items-center"><div><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#1e6b51]">Close a measured blind spot</p><h2 className="mt-1 text-sm font-semibold">Backtest the Clause 4.6 candidate before approval</h2><p className="mt-1 text-xs text-[#66716b]">Approval increases coverage for unlisted settlement deductions; method classification remains honestly ungoverned.</p></div><span className="flex items-center gap-2 text-xs font-semibold text-[#1e6b51]">Open mutation lab <ArrowRight size={14} /></span></Link>
      </main>
    </AppShell>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "green" | "orange" }) {
  const color = tone === "green" ? "text-[#1e6b51]" : tone === "orange" ? "text-[#bd4e24]" : "text-[#17211d]";
  return <div className="panel rounded-xl p-4"><ShieldCheck size={15} className="mb-4 text-[#7a847e]" /><p className={`number-tabular text-2xl font-semibold ${color}`}>{value}</p><p className="mt-1 text-[11px] text-[#727d77]">{label}</p></div>;
}
