"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, CircleAlert, FlaskConical, GitBranch, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

export default function ControlCoveragePage() {
  const { runId } = useParams<{ runId: string }>();
  const coverage = useQuery({
    queryKey: ["control-coverage", runId],
    queryFn: () => api.controlCoverage(runId),
  });

  if (coverage.isPending) {
    return (
      <div className="grid min-h-[calc(100vh-64px)] place-items-center">
        <LoaderCircle className="animate-spin text-[var(--evergreen)]" />
      </div>
    );
  }
  if (coverage.isError || !coverage.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Control coverage" onRetry={() => void coverage.refetch()} />
      </main>
    );
  }
  const data = coverage.data;
  const blindSpots = data.mutation_derived_blind_spots ?? [];

  return (
    <main className="mx-auto max-w-[1240px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow={
          <>
            <GitBranch size={14} /> Control coverage graph
          </>
        }
        title="Which money relationships are governed?"
        subtitle="Runtime coverage counts actual material event edges in this run. Mutation-derived blind spots describe failure modes the control suite cannot detect — they are capability gaps, not ungoverned runtime edges."
        back={{ href: "/", label: "Back to control run" }}
      />

      <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Material edges" value={data.total_material_edges.toLocaleString("en-IN")} />
        <Metric label="Governed" value={data.governed_edges.toLocaleString("en-IN")} tone="green" />
        <Metric label="Ungoverned" value={data.ungoverned_edges.toLocaleString("en-IN")} tone="orange" />
        <Metric label="Control coverage" value={formatPercent(data.coverage_percentage, 2)} tone="green" />
      </section>

      <section className="panel mb-6 overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--paper)]">Material relationship coverage</h2>
          <p className="mt-1 text-xs text-[var(--paper-faint)]">Only relationship types with at least one actual edge in this run appear here</p>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {data.items.map((item) => {
            const rate = item.material_edge_count ? (item.governed_edge_count / item.material_edge_count) * 100 : 100;
            const governed = item.status === "GOVERNED";
            return (
              <div key={item.id} className="p-5">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`grid h-7 w-7 place-items-center rounded-lg ${
                          governed
                            ? "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]"
                            : "bg-[rgba(226,96,79,0.14)] text-[var(--crimson)]"
                        }`}
                      >
                        {governed ? <Check size={13} /> : <CircleAlert size={13} />}
                      </span>
                      <h3 className="font-mono text-xs font-semibold text-[var(--paper)]">{item.relationship}</h3>
                    </div>
                    <p className="ml-9 mt-1 text-xs text-[var(--paper-dim)]">{item.description}</p>
                  </div>
                  <div className="text-left sm:text-right">
                    <Badge status={governed ? "PASS" : "VIOLATION"} label={item.status} />
                    <p className="number-tabular mt-2 font-mono text-[10px] text-[var(--paper-faint)]">
                      {item.governed_edge_count}/{item.material_edge_count} edges
                    </p>
                  </div>
                </div>
                <div className="ml-9 mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]">
                  <div
                    className={`h-full rounded-full ${governed ? "bg-[var(--evergreen)]" : "bg-[var(--crimson)]"}`}
                    style={{ width: `${Math.max(rate, item.material_edge_count ? 1 : 100)}%` }}
                  />
                </div>
                <div className="ml-9 mt-3 flex flex-wrap gap-2">
                  {item.control_ids.map((control) => (
                    <span
                      key={control}
                      className="rounded-md bg-[var(--ink-700)] px-2 py-1 font-mono text-[9px] text-[var(--paper-dim)]"
                    >
                      {control}
                    </span>
                  ))}
                  {item.blind_spot && <p className="w-full text-[10px] leading-5 text-[var(--amber)]">{item.blind_spot}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {blindSpots.length > 0 ? (
        <section className="panel mb-6 overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
              <FlaskConical size={14} className="text-[var(--amber)]" /> Mutation-derived blind spots
            </h2>
            <p className="mt-1 text-xs text-[var(--paper-faint)]">
              Failure modes the control suite cannot detect, established by mutation testing. These are excluded from
              runtime edge counts above.
            </p>
          </div>
          <div className="divide-y divide-[var(--line)]">
            {blindSpots.map((spot) => (
              <div key={spot.id} className="flex flex-col gap-3 p-5 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="grid h-7 w-7 place-items-center rounded-lg bg-[rgba(245,158,11,0.14)] text-[var(--amber)]">
                      <FlaskConical size={13} />
                    </span>
                    <h3 className="font-mono text-xs font-semibold text-[var(--paper)]">{spot.relationship}</h3>
                  </div>
                  <p className="ml-9 mt-1 text-xs text-[var(--paper-dim)]">{spot.description}</p>
                </div>
                <div className="text-left sm:text-right">
                  <span className="rounded-full border border-[rgba(245,158,11,0.4)] bg-[rgba(245,158,11,0.1)] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--amber)]">
                    {spot.failure_mode}
                  </span>
                  <p className="mt-2 font-mono text-[10px] text-[var(--paper-faint)]">{spot.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Link
        href={`/runs/${runId}/mutation-test`}
        className="flex flex-col justify-between gap-4 rounded-2xl border border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.08)] p-5 transition duration-150 sm:flex-row sm:items-center"
      >
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--evergreen)]">Close a measured blind spot</p>
          <h2 className="mt-1 text-sm font-semibold text-[var(--paper)]">Backtest the Clause 4.6 candidate before approval</h2>
          <p className="mt-1 text-xs text-[var(--paper-dim)]">
            Approval raises runtime coverage for unlisted settlement deductions; mutation-derived blind spots shrink only
            when the control suite can actually detect the failure mode.
          </p>
        </div>
        <span className="flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)]">
          Open mutation lab <ArrowRight size={14} />
        </span>
      </Link>
    </main>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "green" | "orange" }) {
  const color =
    tone === "green" ? "text-[var(--evergreen)]" : tone === "orange" ? "text-[var(--crimson)]" : "text-[var(--paper)]";
  return (
    <div className="panel rounded-2xl p-5">
      <ShieldCheck size={15} className="mb-4 text-[var(--paper-faint)]" />
      <p className={`number-tabular font-mono text-2xl font-semibold ${color}`}>{value}</p>
      <p className="mt-1.5 text-xs text-[var(--paper-dim)]">{label}</p>
    </div>
  );
}
