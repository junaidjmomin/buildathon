"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Calculator, Check, RefreshCw } from "lucide-react";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  InlineNotice,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function TemporalReplayPage() {
  const { runId } = useParams<{ runId: string }>();
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });
  const replay = useMutation({
    mutationFn: (controlId: string) => api.temporalReplay(runId, controlId),
  });
  const versions = (controls.data ?? [])
    .filter((control) => control.status === "APPROVED" && control.control_type === "MDR_RATE")
    .sort((a, b) => b.version - a.version);

  if (controls.isPending) {
    return <WorkspaceLoading label="Loading replay controls" />;
  }

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: `/runs/${runId}/mutation-test`, label: "Control quality" }}
          eyebrow={
            <>
              <Calculator size={14} /> Temporal replay
            </>
          }
          title="Replay an approved control version"
          subtitle={
            <>
              Run <span className="font-mono text-[var(--paper)]">{runId}</span> · Recalculate
              historical expectations without changing canonical events or persisted evaluations.
            </>
          }
        />
        <button
          aria-label="Refresh approved control versions"
          className="mt-1 inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3 py-2.5 text-xs font-semibold text-[var(--paper)] transition-colors hover:border-[var(--evergreen)] hover:text-[var(--evergreen)]"
          onClick={() => void controls.refetch()}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={14} /> Refresh versions
        </button>
      </div>

      {controls.isError ? (
        <ErrorState what="Control versions" onRetry={() => void controls.refetch()} />
      ) : versions.length === 0 ? (
        <section className="panel overflow-hidden rounded-xl">
          <EmptySection
            body="Replay becomes available after an effective-dated MDR control has been reviewed and approved."
            title="No replay-eligible control versions"
          />
        </section>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="panel self-start overflow-hidden rounded-xl lg:sticky lg:top-6">
            <SectionHeader
              title="Approved versions"
              description="Choose the effective-dated definition to apply to this run."
              meta={`${versions.length} available`}
            />
            <div className="divide-y divide-[var(--line)]">
              {versions.map((control) => {
                const selected = replay.variables === control.id;
                return (
                  <button
                    aria-pressed={selected}
                    className={`w-full px-5 py-4 text-left transition-colors hover:bg-[var(--ink-600)] disabled:cursor-wait disabled:opacity-60 ${
                      selected ? "bg-[var(--ink-700)]" : "bg-[var(--ink-800)]"
                    }`}
                    disabled={replay.isPending}
                    key={control.id}
                    onClick={() => replay.mutate(control.id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-[var(--paper)]">{control.name}</p>
                        <p className="mt-1 truncate font-mono text-[9px] text-[var(--paper-faint)]">
                          {control.id}
                        </p>
                      </div>
                      <span className="number-tabular font-mono text-xs font-semibold text-[var(--evergreen)]">
                        {control.expected}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2 font-mono text-[10px] text-[var(--paper-dim)]">
                      <span>v{control.version}</span>
                      <span>
                        {control.effective_from} → {control.effective_to ?? "open"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section aria-live="polite" className="panel min-h-[28rem] overflow-hidden rounded-xl">
            {replay.isPending ? (
              <div className="grid min-h-[28rem] place-items-center px-5 text-center" role="status">
                <div>
                  <RefreshCw className="mx-auto animate-spin text-[var(--evergreen)]" size={22} />
                  <p className="mt-3 text-sm font-medium text-[var(--paper)]">Recalculating expectations</p>
                  <p className="mt-1 text-xs text-[var(--paper-dim)]">The source run remains read-only.</p>
                </div>
              </div>
            ) : replay.isError ? (
              <div className="p-5">
                <InlineNotice tone="negative">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                    <span>{replay.error.message}</span>
                    <button
                      className="shrink-0 font-semibold underline underline-offset-2"
                      onClick={() => replay.reset()}
                      type="button"
                    >
                      Clear result
                    </button>
                  </div>
                </InlineNotice>
              </div>
            ) : !replay.data ? (
              <EmptySection
                body="Select an approved version to compare its expected amounts and violations with the run baseline."
                title="Choose a control version"
              />
            ) : (
              <ReplayResult data={replay.data} />
            )}
          </section>
        </div>
      )}
    </main>
  );
}

function ReplayResult({ data }: { data: Awaited<ReturnType<typeof api.temporalReplay>> }) {
  const maxDifference = Math.max(
    ...data.monthly_series.map((entry) => Math.abs(Number(entry.difference_amount))),
    1,
  );

  return (
    <div>
      <SectionHeader
        title="Replay result"
        description={
          <span className="font-mono">
            {data.logical_control_key} · {data.control_id}
          </span>
        }
        meta={<Badge label={`Version ${data.control_version}`} status="INFO" />}
      />
      <div className="p-5">
        <SummaryStrip
          columns="three"
          label="Replay amount comparison"
          items={[
            { label: "Baseline expected", value: formatMoney(data.baseline_expected_amount) },
            { label: "Replay expected", value: formatMoney(data.replay_expected_amount) },
            {
              label: "Difference",
              value: formatMoney(data.difference_amount),
              tone: Number(data.difference_amount) === 0 ? "positive" : "warning",
            },
          ]}
        />

        <dl className="mt-4 grid gap-3 border-y border-[var(--line)] py-4 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-[var(--paper-faint)]">Transactions replayed</dt>
            <dd className="number-tabular mt-1 font-mono font-semibold text-[var(--paper)]">
              {data.transaction_count.toLocaleString("en-IN")}
            </dd>
          </div>
          <div>
            <dt className="text-[var(--paper-faint)]">Baseline violations</dt>
            <dd className="number-tabular mt-1 font-mono font-semibold text-[var(--paper)]">
              {data.baseline_violation_count.toLocaleString("en-IN")}
            </dd>
          </div>
          <div>
            <dt className="text-[var(--paper-faint)]">Replay violations</dt>
            <dd className="number-tabular mt-1 font-mono font-semibold text-[var(--paper)]">
              {data.replay_violation_count.toLocaleString("en-IN")}
            </dd>
          </div>
        </dl>

        <section className="mt-6" aria-labelledby="replay-series-title">
          <div className="flex items-end justify-between gap-3">
            <div>
              <h3 className="text-xs font-semibold text-[var(--paper)]" id="replay-series-title">
                Difference over time
              </h3>
              <p className="mt-1 text-[11px] text-[var(--paper-dim)]">Absolute bar length; signed value shown at right.</p>
            </div>
            <span className="text-[10px] text-[var(--paper-faint)]">{data.monthly_series.length} periods</span>
          </div>
          {data.monthly_series.length ? (
            <div className="mt-3 divide-y divide-[var(--line)] border-y border-[var(--line)]">
              {data.monthly_series.map((item) => {
                const width = (Math.abs(Number(item.difference_amount)) / maxDifference) * 100;
                return (
                  <div className="py-3" key={item.period}>
                    <div className="number-tabular mb-2 flex justify-between gap-3 font-mono text-[10px]">
                      <span className="text-[var(--paper-dim)]">
                        {item.period} · {item.transaction_count.toLocaleString("en-IN")} payments
                      </span>
                      <span className="font-semibold text-[var(--paper)]">{formatMoney(item.difference_amount)}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ink-700)]">
                      <div className="h-full rounded-full bg-[var(--evergreen)]" style={{ width: `${width}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-3 text-xs text-[var(--paper-dim)]">No period-level differences were returned.</p>
          )}
        </section>

        <section className="mt-6" aria-labelledby="replay-evidence-title">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-semibold text-[var(--paper)]" id="replay-evidence-title">
              Changed-payment evidence
            </h3>
            <span className="number-tabular font-mono text-[10px] text-[var(--paper-faint)]">
              {data.evidence.length.toLocaleString("en-IN")} records
            </span>
          </div>
          {data.evidence.length ? (
            <div className="mt-3 max-h-64 overflow-auto rounded-lg border border-[var(--line)]">
              <table className="w-full min-w-[32rem] text-left text-xs">
                <thead className="sticky top-0 bg-[var(--ink-600)] text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">
                  <tr>
                    <th className="px-3 py-2.5" scope="col">Payment</th>
                    <th className="px-3 py-2.5 text-right" scope="col">Difference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--line)]">
                  {data.evidence.map((item, index) => (
                    <tr key={`${String(item.payment_id)}-${index}`}>
                      <td className="px-3 py-2.5 font-mono text-[var(--paper)]">{String(item.payment_id)}</td>
                      <td className="number-tabular px-3 py-2.5 text-right font-mono font-semibold text-[var(--evergreen)]">
                        {formatMoney(String(item.difference))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-3 flex items-center gap-2 text-xs text-[var(--paper-dim)]">
              <Check aria-hidden="true" className="text-[var(--evergreen)]" size={14} /> No payment expectation changed.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
