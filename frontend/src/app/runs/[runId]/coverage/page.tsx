"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, CircleAlert, FlaskConical, GitBranch } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

export default function ControlCoveragePage() {
  const { runId } = useParams<{ runId: string }>();
  const coverage = useQuery({
    queryKey: ["control-coverage", runId],
    queryFn: () => api.controlCoverage(runId),
  });

  if (coverage.isPending) {
    return <WorkspaceLoading label="Loading control coverage" />;
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
        back={{ href: "/", label: "Control run" }}
        eyebrow={
          <>
            <GitBranch size={14} /> Coverage evidence
          </>
        }
        title="Governed money relationships"
        subtitle={
          <>
            Run <span className="font-mono text-[var(--paper)]">{runId}</span> · Runtime edge
            coverage is separated from capability gaps proven by mutation tests.
          </>
        }
      />

      <SummaryStrip
        className="mb-6"
        label="Coverage summary"
        items={[
          { label: "Material edges", value: data.total_material_edges.toLocaleString("en-IN") },
          {
            label: "Governed",
            value: data.governed_edges.toLocaleString("en-IN"),
            tone: "positive",
          },
          {
            label: "Not fully governed",
            value: (data.partially_governed_edges + data.ungoverned_edges).toLocaleString("en-IN"),
            detail: `${data.ungoverned_edges.toLocaleString("en-IN")} ungoverned`,
            tone: data.partially_governed_edges + data.ungoverned_edges ? "warning" : "positive",
          },
          {
            label: "Coverage",
            value: formatPercent(data.coverage_percentage, 2),
            tone: data.ungoverned_edges ? "warning" : "positive",
          },
        ]}
      />

      <section className="panel mb-6 overflow-hidden rounded-xl">
        <SectionHeader
          title="Material relationship inventory"
          description="Only relationship types observed in this run are counted. Each row shows the controls responsible for governance."
          meta={`${data.items.length.toLocaleString("en-IN")} relationship types`}
        />
        {data.items.length ? (
          <div className="divide-y divide-[var(--line)]">
            {data.items.map((item) => {
              const rate = item.material_edge_count
                ? (item.governed_edge_count / item.material_edge_count) * 100
                : 100;
              const governed = item.status === "GOVERNED";
              const partial = item.status === "PARTIALLY_GOVERNED";
              return (
                <article className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_10rem_10rem] lg:items-center" key={item.id}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {governed ? (
                        <Check aria-hidden="true" className="shrink-0 text-[var(--evergreen)]" size={15} />
                      ) : (
                        <CircleAlert
                          aria-hidden="true"
                          className={`shrink-0 ${partial ? "text-[var(--amber)]" : "text-[var(--crimson)]"}`}
                          size={15}
                        />
                      )}
                      <h3 className="truncate font-mono text-xs font-semibold text-[var(--paper)]">
                        {item.relationship}
                      </h3>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{item.description}</p>
                    {item.control_ids.length ? (
                      <p className="mt-2 truncate font-mono text-[10px] text-[var(--paper-faint)]">
                        {item.control_ids.join(" · ")}
                      </p>
                    ) : (
                      <p className="mt-2 text-[10px] text-[var(--paper-faint)]">No governing control linked</p>
                    )}
                    {item.blind_spot ? (
                      <p className="mt-2 text-[10px] leading-4 text-[var(--amber)]">{item.blind_spot}</p>
                    ) : null}
                  </div>
                  <div>
                    <div className="number-tabular mb-2 flex justify-between font-mono text-[10px] text-[var(--paper-dim)]">
                      <span>{formatPercent(String(rate / 100), 0)}</span>
                      <span>
                        {item.governed_edge_count}/{item.material_edge_count}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]">
                      <div
                        className={`h-full rounded-full ${
                          governed ? "bg-[var(--evergreen)]" : partial ? "bg-[var(--amber)]" : "bg-[var(--crimson)]"
                        }`}
                        style={{ width: `${Math.max(rate, item.material_edge_count ? 1 : 100)}%` }}
                      />
                    </div>
                  </div>
                  <div className="lg:text-right">
                    <Badge
                      label={item.status.replaceAll("_", " ")}
                      status={governed ? "PASS" : partial ? "UNRESOLVED" : "VIOLATION"}
                    />
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptySection
            body="This run has no material relationship edges to assess."
            title="No runtime coverage data"
          />
        )}
      </section>

      <section className="panel mb-6 overflow-hidden rounded-xl">
        <SectionHeader
          title="Mutation-derived capability gaps"
          description="These are failure modes the current control suite could not detect. They are not included in runtime edge counts."
          meta={blindSpots.length ? <Badge label={`${blindSpots.length} open`} status="UNRESOLVED" /> : null}
        />
        {blindSpots.length ? (
          <div className="divide-y divide-[var(--line)]">
            {blindSpots.map((spot) => (
              <article className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start" key={spot.id}>
                <div>
                  <div className="flex items-center gap-2">
                    <FlaskConical aria-hidden="true" className="shrink-0 text-[var(--amber)]" size={14} />
                    <h3 className="font-mono text-xs font-semibold text-[var(--paper)]">{spot.relationship}</h3>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{spot.description}</p>
                  <p className="mt-2 font-mono text-[10px] text-[var(--paper-faint)]">{spot.reason}</p>
                </div>
                <Badge label={spot.failure_mode.replaceAll("_", " ")} status="UNRESOLVED" />
              </article>
            ))}
          </div>
        ) : (
          <EmptySection
            body="The latest mutation evidence did not report an undetected failure mode for this run."
            title="No capability gaps reported"
          />
        )}
      </section>

      <div className="flex justify-end">
        <Link
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-800)] transition-opacity hover:opacity-90"
          href={`/runs/${runId}/mutation-test`}
        >
          Open mutation testing <ArrowRight aria-hidden="true" size={14} />
        </Link>
      </div>
    </main>
  );
}
