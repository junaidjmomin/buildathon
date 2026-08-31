"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Beaker,
  Check,
  CircleAlert,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { Badge, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  InlineNotice,
  SectionHeader,
  SummaryStrip,
} from "@/components/ui/workspace";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import type { Control, MutationTestSummary } from "@/types/api";

const humanize = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (character) => character.toUpperCase());

export default function MutationTestPage() {
  const { runId } = useParams<{ runId: string }>();
  const mutation = useMutation({ mutationFn: () => api.runMutationTest(runId) });
  const autoRunStarted = useRef(false);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_APP_MODE !== "production" && !autoRunStarted.current) {
      autoRunStarted.current = true;
      mutation.mutate();
    }
    // Run one isolated suite on first entry in demo mode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="mx-auto max-w-[1240px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: "/", label: "Control run" }}
          eyebrow={
            <>
              <Beaker size={14} /> Control quality
            </>
          }
          title="Mutation test the control suite"
          subtitle={
            <>
              Run <span className="font-mono text-[var(--paper)]">{runId}</span> · Inject
              isolated faults into a derived copy and record which failure modes remain unseen.
            </>
          }
        />
        <button
          aria-busy={mutation.isPending}
          className="mt-1 inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-800)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
          type="button"
        >
          <RefreshCw aria-hidden="true" className={mutation.isPending ? "animate-spin" : ""} size={14} />
          {mutation.data ? "Run new suite" : "Run mutation suite"}
        </button>
      </div>

      {mutation.isPending ? (
        <section className="panel grid min-h-72 place-items-center rounded-xl px-5 text-center" role="status">
          <div>
            <RefreshCw className="mx-auto animate-spin text-[var(--evergreen)]" size={22} />
            <p className="mt-3 text-sm font-medium text-[var(--paper)]">Executing isolated mutations</p>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">Canonical run data remains read-only.</p>
          </div>
        </section>
      ) : mutation.isError ? (
        <InlineNotice tone="negative">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <span>{mutation.error.message}</span>
            <button className="shrink-0 font-semibold underline underline-offset-2" onClick={() => mutation.mutate()} type="button">
              Retry suite
            </button>
          </div>
        </InlineNotice>
      ) : mutation.data ? (
        <MutationResults data={mutation.data} runId={runId} />
      ) : (
        <section className="panel overflow-hidden rounded-xl">
          <EmptySection
            body="Start an isolated test when you are ready to create a new control-quality result. Source data is never mutated."
            title="No mutation result recorded in this session"
          />
        </section>
      )}
    </main>
  );
}

function MutationResults({ data, runId }: { data: MutationTestSummary; runId: string }) {
  const missed = data.results.filter((result) => !result.detected);
  const missedControlTypes = new Set(missed.map((result) => result.expected_control_type));
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });
  const candidates = (controls.data ?? []).filter(
    (control) => control.status !== "APPROVED" && missedControlTypes.has(control.control_type),
  );

  return (
    <div className="space-y-6">
      <SummaryStrip
        columns="five"
        label="Mutation suite result"
        items={[
          { label: "Injected", value: data.mutation_count.toLocaleString("en-IN") },
          { label: "Detected", value: data.detected_count.toLocaleString("en-IN"), tone: "positive" },
          {
            label: "Missed",
            value: data.missed_count.toLocaleString("en-IN"),
            tone: data.missed_count ? "negative" : "positive",
          },
          {
            label: "Detection rate",
            value: formatPercent(data.mutation_detection_rate, 0),
            tone: data.missed_count ? "warning" : "positive",
          },
          {
            label: "False positives",
            value: data.false_positive_count.toLocaleString("en-IN"),
            tone: data.false_positive_count ? "negative" : "positive",
          },
        ]}
      />

      <InlineNotice tone={data.canonical_data_unchanged ? "positive" : "negative"}>
        <span className="flex items-start gap-2">
          {data.canonical_data_unchanged ? (
            <Check aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
          ) : (
            <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
          )}
          <span>
            <strong>{data.canonical_data_unchanged ? "Canonical dataset unchanged." : "Canonical dataset check failed."}</strong>{" "}
            Each mutation is expected to run against a derived copy of the source run.
          </span>
        </span>
      </InlineNotice>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
        <section className="panel overflow-hidden rounded-xl">
          <SectionHeader
            title="Detection coverage by fault type"
            description="Exact detected and injected counts from this suite."
            meta={`${data.coverage.length.toLocaleString("en-IN")} fault types`}
          />
          {data.coverage.length ? (
            <div className="divide-y divide-[var(--line)]">
              {data.coverage.map((item) => {
                const rate = item.injected ? (item.detected / item.injected) * 100 : 0;
                const complete = item.detected === item.injected;
                return (
                  <div className="px-5 py-4" key={item.mutation_type}>
                    <div className="mb-2 flex items-center justify-between gap-4 text-xs">
                      <span className="font-medium text-[var(--paper)]">{humanize(item.mutation_type)}</span>
                      <span
                        className={`number-tabular font-mono font-semibold ${
                          complete ? "text-[var(--evergreen)]" : "text-[var(--crimson)]"
                        }`}
                      >
                        {item.detected}/{item.injected} · {rate.toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]">
                      <div
                        className={`h-full rounded-full ${complete ? "bg-[var(--evergreen)]" : "bg-[var(--crimson)]"}`}
                        style={{ width: `${rate}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptySection body="This result did not include fault-type coverage." title="No coverage breakdown" />
          )}
        </section>

        <div className="space-y-5">
          <section className="panel overflow-hidden rounded-xl">
            <SectionHeader
              title="Open control blind spots"
              description="Missed mutations that require a control or evidence decision."
              meta={<Badge label={`${missed.length} open`} status={missed.length ? "UNRESOLVED" : "PASS"} />}
            />
            {missed.length ? (
              <div className="divide-y divide-[var(--line)]">
                {missed.map((item) => (
                  <article className="px-5 py-4" key={item.id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--crimson)]">
                          {item.id} · {humanize(item.mutation_type)}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[var(--paper)]">{item.description}</p>
                      </div>
                      <X aria-hidden="true" className="shrink-0 text-[var(--crimson)]" size={15} />
                    </div>
                    <dl className="mt-3 grid gap-3 border-t border-[var(--line)] pt-3 text-[10px] sm:grid-cols-2">
                      <div>
                        <dt className="text-[var(--paper-faint)]">Expected control type</dt>
                        <dd className="mt-1 font-mono font-semibold text-[var(--paper)]">
                          {humanize(item.expected_control_type)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--paper-faint)]">Why it was missed</dt>
                        <dd className="mt-1 font-mono font-semibold text-[var(--paper)]">
                          {item.blind_spot_reason ? humanize(item.blind_spot_reason) : "No reason supplied"}
                        </dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <EmptySection
                body="Every injected failure mode was detected by the current control suite."
                title="No blind spots detected"
              />
            )}
          </section>

          {controls.isPending ? (
            <InlineNotice>Checking for draft controls that match the missed fault types…</InlineNotice>
          ) : controls.isError ? (
            <InlineNotice tone="negative">Candidate controls could not be loaded.</InlineNotice>
          ) : candidates.length ? (
            candidates.map((candidate) => <CandidateBacktest candidate={candidate} key={candidate.id} runId={runId} />)
          ) : missed.length ? (
            <InlineNotice>
              No draft control currently matches the expected control types above. Add a sourced proposal from an agreement before backtesting.
            </InlineNotice>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CandidateBacktest({ candidate, runId }: { candidate: Control; runId: string }) {
  const queryClient = useQueryClient();
  const backtest = useMutation({ mutationFn: () => api.backtestControl(candidate.id, runId) });
  const approve = useMutation({
    mutationFn: () => api.approveControl(candidate.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["controls"] }),
  });

  return (
    <section className="panel overflow-hidden rounded-xl">
      <SectionHeader
        title={candidate.name}
        description={`${candidate.expected} · ${candidate.scope}`}
        meta={<Badge label={approve.isSuccess ? "Approved" : candidate.status} status={approve.isSuccess ? "PASS" : "DRAFT"} />}
      />
      <div className="p-5">
        <p className="font-mono text-[10px] text-[var(--paper-faint)]">
          {candidate.source_clause} · {candidate.id}
        </p>
        {!backtest.data ? (
          <div className="mt-4">
            <p className="text-xs leading-5 text-[var(--paper-dim)]">
              Compare this sourced candidate against clean historical data and the current mutation suite before activation.
            </p>
            <button
              aria-busy={backtest.isPending}
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
              disabled={backtest.isPending}
              onClick={() => backtest.mutate()}
              type="button"
            >
              <TrendingUp aria-hidden="true" size={13} />
              {backtest.isPending ? "Running backtest…" : "Backtest candidate"}
            </button>
          </div>
        ) : (
          <div className="mt-4">
            <SummaryStrip
              columns="three"
              label={`${candidate.name} backtest result`}
              items={[
                {
                  label: "Before",
                  value: `${backtest.data.before.detected_count}/${backtest.data.before.mutation_count}`,
                  detail: "mutations detected",
                },
                {
                  label: "With candidate",
                  value: `${backtest.data.after.detected_count}/${backtest.data.after.mutation_count}`,
                  detail: "mutations detected",
                  tone: "positive",
                },
                {
                  label: "Coverage delta",
                  value: formatPercent(backtest.data.detection_rate_delta, 0),
                  detail: `${backtest.data.false_positive_delta} false-positive delta`,
                  tone: "positive",
                },
              ]}
            />
            {!approve.isSuccess ? (
              <button
                aria-busy={approve.isPending}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
                disabled={approve.isPending}
                onClick={() => approve.mutate()}
                type="button"
              >
                <ShieldCheck aria-hidden="true" size={13} />
                {approve.isPending ? "Approving…" : "Approve control"}
              </button>
            ) : (
              <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)]" role="status">
                <Check aria-hidden="true" size={13} /> Approved explicitly for future suites.
              </p>
            )}
          </div>
        )}
        {backtest.isError ? <InlineNotice className="mt-3" tone="negative">{backtest.error.message}</InlineNotice> : null}
        {approve.isError ? <InlineNotice className="mt-3" tone="negative">{approve.error.message}</InlineNotice> : null}
      </div>
    </section>
  );
}
