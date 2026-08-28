"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Calculator, LoaderCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function TemporalReplayPage() {
  const { runId } = useParams<{ runId: string }>();
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });
  const replay = useMutation({ mutationFn: (controlId: string) => api.temporalReplay(runId, controlId) });
  const versions = controls.data?.filter((control) => control.logical_control_key === "DOMESTIC_CARD_MDR") ?? [];

  return (
    <main className="mx-auto max-w-[1120px] px-5 py-7 md:px-8 md:py-9">
      <Link
        href={`/runs/${runId}/mutation-test`}
        className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[var(--paper-dim)] transition-colors duration-150 hover:text-[var(--paper)]"
      >
        <ArrowLeft size={14} /> Back to control quality
      </Link>
      <div className="mb-7 flex items-end justify-between gap-4">
        <div>
          <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--evergreen)]">
            <Calculator size={14} /> Temporal replay
          </p>
          <h1 className="text-3xl font-semibold tracking-[-0.035em] text-[var(--paper)]">
            What if this control version had applied?
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--paper-dim)]">
            Recalculate historical card fees under an approved effective-dated MDR version. Canonical events and persisted
            evaluations remain unchanged.
          </p>
        </div>
        <button
          type="button"
          onClick={() => controls.refetch()}
          className="rounded-lg border border-[var(--line)] bg-[var(--ink-800)] p-2.5 text-[var(--evergreen)] transition duration-150 hover:bg-[var(--ink-600)]"
          aria-label="Refresh control versions"
        >
          <RefreshCw size={15} />
        </button>
      </div>
      {controls.isPending ? (
        <LoaderCircle className="mx-auto mt-20 animate-spin text-[var(--evergreen)]" />
      ) : controls.isError ? (
        <ErrorState what="Control versions" onRetry={() => void controls.refetch()} />
      ) : versions.length === 0 ? (
        <div className="panel rounded-2xl p-7 text-sm text-[var(--paper-dim)]">
          No approved MDR versions are registered for this tenant.
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
          <section className="panel rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-[var(--paper)]">Approved MDR versions</h2>
            <p className="mt-1 text-xs text-[var(--paper-faint)]">Select a version to replay the current run.</p>
            <div className="mt-4 space-y-2">
              {versions.map((control) => (
                <button
                  key={control.id}
                  type="button"
                  onClick={() => replay.mutate(control.id)}
                  disabled={replay.isPending}
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-4 text-left transition duration-150 hover:border-[rgba(47,189,127,0.45)] disabled:opacity-60"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="number-tabular font-mono text-[10px] text-[var(--paper-faint)]">
                      v{control.version} · {control.id}
                    </span>
                    <span className="number-tabular font-mono text-xs font-semibold text-[var(--evergreen)]">
                      {control.expected}
                    </span>
                  </div>
                  <p className="number-tabular mt-2 font-mono text-[11px] text-[var(--paper-dim)]">
                    {control.effective_from} → {control.effective_to ?? "open"}
                  </p>
                </button>
              ))}
            </div>
          </section>
          <section className="panel min-h-72 rounded-2xl p-5">
            {replay.isPending ? (
              <div className="grid h-60 place-items-center text-center">
                <div>
                  <LoaderCircle className="mx-auto mb-3 animate-spin text-[var(--evergreen)]" />
                  <p className="text-sm font-medium text-[var(--paper)]">Replaying deterministic fee expectations…</p>
                </div>
              </div>
            ) : replay.isError ? (
              <div className="grid h-60 place-items-center text-center text-sm text-[var(--crimson)]">
                Replay failed.{" "}
                <button type="button" onClick={() => replay.reset()} className="font-semibold underline underline-offset-2">
                  Dismiss
                </button>
              </div>
            ) : !replay.data ? (
              <div className="grid h-60 place-items-center text-center text-sm text-[var(--paper-dim)]">
                <div>
                  <Calculator className="mx-auto mb-3 text-[var(--evergreen)]" />
                  <p>Select an approved control version to begin.</p>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--evergreen)]">
                  Replay result · v{replay.data.control_version}
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <Metric label="Baseline expected" value={formatMoney(replay.data.baseline_expected_amount)} />
                  <Metric label="Replay expected" value={formatMoney(replay.data.replay_expected_amount)} />
                  <Metric label="Difference" value={formatMoney(replay.data.difference_amount)} />
                </div>
                <div className="mt-5 grid gap-3 text-xs text-[var(--paper-dim)] sm:grid-cols-3">
                  <div>
                    Card transactions{" "}
                    <strong className="number-tabular font-mono text-[var(--paper)]">{replay.data.transaction_count}</strong>
                  </div>
                  <div>
                    Baseline violations{" "}
                    <strong className="number-tabular font-mono text-[var(--paper)]">
                      {replay.data.baseline_violation_count}
                    </strong>
                  </div>
                  <div>
                    Replay violations{" "}
                    <strong className="number-tabular font-mono text-[var(--paper)]">
                      {replay.data.replay_violation_count}
                    </strong>
                  </div>
                </div>
                <div className="mt-5 border-t border-[var(--line)] pt-4">
                  <p className="text-xs font-semibold text-[var(--paper)]">MDR difference over time</p>
                  <div className="mt-3 space-y-2">
                    {replay.data.monthly_series.map((item) => {
                      const max = Math.max(
                        ...replay.data!.monthly_series.map((entry) => Math.abs(Number(entry.difference_amount))),
                        1,
                      );
                      const width = (Math.abs(Number(item.difference_amount)) / max) * 100;
                      return (
                        <div key={item.period}>
                          <div className="number-tabular mb-1 flex justify-between font-mono text-[10px] text-[var(--paper-dim)]">
                            <span>
                              {item.period} · {item.transaction_count} card payments
                            </span>
                            <span className="font-semibold text-[var(--paper)]">{formatMoney(item.difference_amount)}</span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-[var(--ink-700)]">
                            <div
                              className="h-full rounded-full bg-[var(--evergreen)]"
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="mt-5 border-t border-[var(--line)] pt-4">
                  <p className="text-xs font-semibold text-[var(--paper)]">
                    Evidence ({replay.data.evidence.length} changed payments)
                  </p>
                  <div className="mt-2 max-h-56 space-y-2 overflow-auto">
                    {replay.data.evidence.slice(0, 20).map((item) => (
                      <div
                        key={String(item.payment_id)}
                        className="flex justify-between gap-3 rounded-lg bg-[var(--ink-700)] px-3 py-2 text-[10px]"
                      >
                        <span className="number-tabular font-mono text-[var(--paper)]">{String(item.payment_id)}</span>
                        <span className="number-tabular font-mono font-semibold text-[var(--evergreen)]">
                          {formatMoney(String(item.difference))}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-3">
      <p className="text-[10px] text-[var(--paper-faint)]">{label}</p>
      <p className="number-tabular mt-1 font-mono text-lg font-semibold text-[var(--paper)]">{value}</p>
    </div>
  );
}
