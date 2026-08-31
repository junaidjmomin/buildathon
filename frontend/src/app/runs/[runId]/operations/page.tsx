"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowRight, Check, Clock3, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ErrorState, PageHeader } from "@/components/ui/primitives";
import {
  InlineNotice,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { api } from "@/lib/api";

export default function RunOperationsPage() {
  const { runId } = useParams<{ runId: string }>();
  const metrics = useQuery({
    queryKey: ["operational-metrics", runId],
    queryFn: () => api.operationalMetrics(runId),
  });

  if (metrics.isPending) {
    return <WorkspaceLoading label="Loading run operations" />;
  }
  if (metrics.isError || !metrics.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Run operational metrics" onRetry={() => void metrics.refetch()} />
      </main>
    );
  }

  const data = metrics.data;
  const durations = Object.entries(data.stage_durations_ms);
  const maxDuration = Math.max(...durations.map(([, value]) => value), 1);
  const completed = data.failed_stage_count === 0 && data.completed_stage_count === data.stage_count;

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        back={{ href: "/", label: "Control run" }}
        eyebrow={
          <>
            <Activity size={14} /> Run operations
          </>
        }
        title="Pipeline health and throughput"
        subtitle={
          <>
            Run <span className="font-mono text-[var(--paper)]">{runId}</span> · Persisted stage
            timings and output counters
          </>
        }
      />

      <SummaryStrip
        className="mb-6"
        columns="five"
        label="Run health summary"
        items={[
          {
            label: "Run state",
            value: completed ? "Complete" : data.failed_stage_count ? "Attention" : "In progress",
            detail: `${data.completed_stage_count} of ${data.stage_count} stages`,
            tone: completed ? "positive" : data.failed_stage_count ? "negative" : "warning",
          },
          {
            label: "Failed stages",
            value: data.failed_stage_count.toLocaleString("en-IN"),
            tone: data.failed_stage_count ? "negative" : "positive",
          },
          {
            label: "Total processing",
            value: `${data.total_processing_ms.toLocaleString("en-IN")} ms`,
          },
          {
            label: "Events created",
            value: data.events_created.toLocaleString("en-IN"),
          },
          {
            label: "Evaluations",
            value: data.evaluations_created.toLocaleString("en-IN"),
          },
        ]}
      />

      {data.failed_stage_count > 0 ? (
        <InlineNotice className="mb-5" tone="negative">
          <span className="flex items-start gap-2">
            <X className="mt-0.5 shrink-0" size={14} />
            {data.failed_stage_count.toLocaleString("en-IN")} pipeline stage
            {data.failed_stage_count === 1 ? "" : "s"} failed. Review the persisted backend stage
            log before retrying this run.
          </span>
        </InlineNotice>
      ) : null}

      <section className="panel overflow-hidden rounded-xl">
        <SectionHeader
          title="Pipeline stage timings"
          description="Relative bars make bottlenecks visible; the exact persisted duration remains the source of truth."
          meta={`${durations.length.toLocaleString("en-IN")} recorded`}
        />
        {durations.length ? (
          <ol className="divide-y divide-[var(--line)]" aria-label="Pipeline stage durations">
            {durations.map(([stage, duration], index) => (
              <li className="grid gap-3 px-5 py-4 sm:grid-cols-[2rem_minmax(0,1fr)_auto] sm:items-center" key={stage}>
                <span className="number-tabular font-mono text-[10px] text-[var(--paper-faint)]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-xs font-medium text-[var(--paper)]">
                    <Check aria-hidden="true" className="shrink-0 text-[var(--evergreen)]" size={14} />
                    <span className="truncate">{stage.replaceAll("_", " ")}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]">
                    <div
                      className="h-full rounded-full bg-[var(--evergreen)]"
                      style={{ width: `${Math.max(2, (duration / maxDuration) * 100)}%` }}
                    />
                  </div>
                </div>
                <span className="number-tabular flex items-center gap-1 font-mono text-xs text-[var(--paper-dim)]">
                  <Clock3 aria-hidden="true" size={12} />
                  {duration.toLocaleString("en-IN")} ms
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="px-5 py-10 text-center text-xs text-[var(--paper-dim)]">
            No stage timings were recorded for this run.
          </p>
        )}
      </section>

      <div className="mt-5 flex justify-end">
        <Link
          className="inline-flex items-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] transition-colors hover:border-[var(--evergreen)] hover:text-[var(--evergreen)]"
          href={`/runs/${runId}/coverage`}
        >
          Inspect control coverage <ArrowRight aria-hidden="true" size={14} />
        </Link>
      </div>
    </main>
  );
}
