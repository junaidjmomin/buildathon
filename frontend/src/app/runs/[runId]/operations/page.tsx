"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Check, Clock3, LoaderCircle, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function RunOperationsPage() {
  const { runId } = useParams<{ runId: string }>();
  const metrics = useQuery({
    queryKey: ["operational-metrics", runId],
    queryFn: () => api.operationalMetrics(runId),
  });

  if (metrics.isPending) {
    return <div className="grid min-h-[calc(100vh-64px)] place-items-center"><LoaderCircle className="animate-spin text-[var(--evergreen)]" /></div>;
  }
  if (metrics.isError || !metrics.data) {
    return <main className="mx-auto max-w-3xl px-5 py-10 md:px-8"><ErrorState what="Run operational metrics" onRetry={() => void metrics.refetch()} /></main>;
  }
  const data = metrics.data;
  const durations = Object.entries(data.stage_durations_ms);
  const maxDuration = Math.max(...durations.map(([, value]) => value), 1);

  return (
    <main className="mx-auto max-w-[1100px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow={<><Activity size={14} /> Run operations</>}
        title="Is the control run healthy?"
        subtitle="Stage-level timings and durable counters make throughput and partial failures visible without changing financial results."
        back={{ href: "/", label: "Back to control run" }}
      />

      <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="Stages" value={`${data.completed_stage_count}/${data.stage_count}`} />
        <Metric label="Failed stages" value={String(data.failed_stage_count)} tone={data.failed_stage_count ? "bad" : "good"} />
        <Metric label="Total processing" value={`${data.total_processing_ms} ms`} />
        <Metric label="Events created" value={data.events_created.toLocaleString("en-IN")} />
        <Metric label="Evaluations" value={data.evaluations_created.toLocaleString("en-IN")} />
      </section>

      <section className="panel overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--paper)]">Pipeline stages</h2>
          <p className="mt-1 text-xs text-[var(--paper-faint)]">Durations are read from the run’s persisted stage log.</p>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {durations.length ? durations.map(([stage, duration]) => (
            <div key={stage} className="px-5 py-4">
              <div className="flex items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-2 font-medium text-[var(--paper)]"><Check size={14} className="text-[var(--evergreen)]" />{stage}</div>
                <span className="number-tabular flex items-center gap-1 font-mono text-[var(--paper-dim)]"><Clock3 size={12} />{duration} ms</span>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]"><div className="h-full rounded-full bg-[var(--evergreen)]" style={{ width: `${Math.max(2, (duration / maxDuration) * 100)}%` }} /></div>
            </div>
          )) : <div className="px-5 py-10 text-center text-xs text-[var(--paper-dim)]">No stage timings were recorded for this run.</div>}
        </div>
      </section>

      {data.failed_stage_count > 0 && <div className="mt-5 flex items-center gap-2 rounded-xl border border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.08)] px-4 py-3 text-xs text-[var(--crimson)]"><X size={14} /> One or more stages failed. Retry the run after checking the backend stage log.</div>}
      <Link href={`/runs/${runId}/coverage`} className="mt-5 inline-flex rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold text-[var(--paper)] transition-colors hover:border-[var(--evergreen)]">Inspect control coverage</Link>
    </main>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "good" | "bad" }) {
  const color = tone === "good" ? "text-[var(--evergreen)]" : tone === "bad" ? "text-[var(--crimson)]" : "text-[var(--paper)]";
  return <div className="panel rounded-2xl p-5"><p className={`number-tabular font-mono text-2xl font-semibold ${color}`}>{value}</p><p className="mt-1.5 text-xs text-[var(--paper-dim)]">{label}</p></div>;
}
