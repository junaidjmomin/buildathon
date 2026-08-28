"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  Check,
  CircleDollarSign,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  Scale,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { AgentTraceStep } from "@/types/api";

export default function RootCausePage() {
  const { rootCauseId } = useParams<{ rootCauseId: string }>();
  const root = useQuery({
    queryKey: ["root-cause", rootCauseId],
    queryFn: () => api.rootCause(rootCauseId),
  });
  const investigation = useMutation({
    mutationFn: () => api.investigateRootCause(rootCauseId),
  });

  if (root.isPending) {
    return (
      <div className="grid min-h-[calc(100vh-64px)] place-items-center">
        <LoaderCircle
          aria-label="Loading root cause"
          className="animate-spin text-[var(--evergreen)]"
        />
      </div>
    );
  }
  if (!root.data) {
    return (
      <main className="p-8" role="alert">
        Root cause could not be loaded.
      </main>
    );
  }
  const data = root.data;
  const execution = investigation.data;

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[var(--paper-dim)] transition-colors duration-150 hover:text-[var(--paper)]"
      >
        <ArrowLeft size={14} /> Back to control run
      </Link>

      <section className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--evergreen)]">
            <GitBranch size={14} /> Systemic root cause
          </p>
          <h1 className="text-3xl font-semibold tracking-[-0.035em] text-[var(--paper)]">{data.title}</h1>
          <p className="mt-2 text-sm text-[var(--paper-dim)]">
            {data.category} · <span className="font-mono">{data.id}</span>
          </p>
        </div>
        <div className="rounded-xl border border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)] px-5 py-3 text-right">
          <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--crimson)]">
            Verified impact
          </p>
          <p className="number-tabular mt-1 font-mono text-2xl font-semibold text-[var(--crimson)]">
            {formatMoney(data.verified_impact)}
          </p>
        </div>
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          icon={ShieldAlert}
          label="Affected payments"
          value={String(data.affected_count)}
        />
        <Metric
          icon={GitBranch}
          label="Primary violations"
          value={String(data.primary_violation_count)}
        />
        <Metric
          icon={GitBranch}
          label="Downstream effects"
          value={String(data.downstream_effect_count)}
        />
        <Metric
          icon={CircleDollarSign}
          label="Expected → observed"
          value={`${data.expected_value} → ${data.observed_value}`}
        />
      </section>

      <section className="panel mb-5 rounded-2xl p-5">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
              <BrainCircuit size={17} className="text-[var(--evergreen)]" />
              {execution?.orchestration_used ? `${execution.orchestration_provider} orchestration` : "Deterministic investigation"}
            </h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--paper-dim)]">
              Orchestrates evidence collection, structured hypotheses, deterministic
              verification, bounded retries, and human workflow. It cannot change financial
              truth or controls.
            </p>
          </div>
          <button
            type="button"
            onClick={() => investigation.mutate()}
            disabled={investigation.isPending}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-xs font-semibold text-[#06120c] transition-opacity duration-150 disabled:cursor-wait disabled:opacity-60"
          >
            {investigation.isPending ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : execution ? (
              <RefreshCw size={14} />
            ) : (
              <BrainCircuit size={14} />
            )}
            {execution ? "Run a fresh investigation" : "Run bounded investigation"}
          </button>
        </div>
        {investigation.error ? (
          <p className="mt-4 text-xs text-[var(--crimson)]" role="alert">
            {investigation.error instanceof ApiError
              ? investigation.error.message
              : "The investigation could not be started."}
          </p>
        ) : null}
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
              <GitBranch size={16} className="text-[var(--evergreen)]" /> Execution trace
            </h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">
              Explicit nodes, branches, retries, and authority boundaries
            </p>
          </div>
          <div className="p-5">
            {!execution ? (
              <EmptyTrace pending={investigation.isPending} />
            ) : (
              <ol className="space-y-3" aria-label="Agent execution trace">
                {execution.trace.map((step, index) => (
                  <TraceRow key={`${step.sequence}-${step.node}-${index}`} step={step} />
                ))}
              </ol>
            )}
          </div>
        </div>

        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
              <Scale size={16} className="text-[var(--evergreen)]" /> Hypotheses and verdict
            </h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">
              Model proposals remain subordinate to deterministic verification
            </p>
          </div>
          <div className="p-5">
            {!execution ? (
              <div className="grid min-h-64 place-items-center text-center">
                <div>
                  <Scale className="mx-auto mb-3 text-[var(--paper-faint)]" />
                  <p className="text-sm font-medium text-[var(--paper)]">No agent conclusion</p>
                  <p className="mt-1 text-xs text-[var(--paper-dim)]">Nothing is inferred in advance.</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-[10px]">
                  <span className="rounded-full border border-[rgba(95,182,217,0.35)] bg-[rgba(95,182,217,0.14)] px-2.5 py-1 font-semibold text-[var(--sky)]">
                    {execution.llm_used
                      ? `${execution.llm_provider ?? "LLM"} · ${execution.llm_model ?? "configured model"}`
                      : "Deterministic fallback"}
                  </span>
                  <span className="number-tabular font-mono text-[var(--paper-dim)]">
                    {execution.attempt_count} attempt
                    {execution.attempt_count === 1 ? "" : "s"}
                  </span>
                </div>
                {execution.hypotheses.map((hypothesis, index) => (
                  <article
                    key={hypothesis.hypothesis_id}
                    className="rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-4"
                  >
                    <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--paper-faint)]">
                      Attempt {index + 1} · {hypothesis.kind.replaceAll("_", " ")}
                    </p>
                    <p className="mt-2 text-sm font-medium leading-6 text-[var(--paper)]">
                      “{hypothesis.statement}”
                    </p>
                    <p className="mt-2 text-[10px] leading-5 text-[var(--paper-dim)]">
                      {hypothesis.rationale}
                    </p>
                  </article>
                ))}
                {execution.verification ? (
                  <div
                    className={`rounded-xl border p-4 ${
                      execution.status === "PROVEN"
                        ? "border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.14)]"
                        : "border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.14)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--paper-faint)]">
                          Deterministic final result
                        </p>
                        <p className={`mt-1 text-xl font-semibold ${execution.status === "PROVEN" ? "text-[var(--evergreen)]" : "text-[var(--crimson)]"}`}>{execution.status}</p>
                      </div>
                      {execution.status === "PROVEN" ? (
                        <Check size={22} className="text-[var(--evergreen)]" />
                      ) : (
                        <TriangleAlert size={22} className="text-[var(--crimson)]" />
                      )}
                    </div>
                    <p className="mt-3 text-xs font-semibold text-[var(--paper)]">
                      {execution.verification.classification.replaceAll("_", " ")}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">
                      {execution.verification.conclusion}
                    </p>
                    {execution.case_id ? (
                      <p className="mt-3 text-[10px] font-semibold text-[var(--evergreen)]">
                        Evidence case: <span className="font-mono">{execution.case_id}</span>
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function EmptyTrace({ pending }: { pending: boolean }) {
  return (
    <div className="grid min-h-64 place-items-center text-center" aria-live="polite">
      <div>
        {pending ? (
          <LoaderCircle className="mx-auto mb-3 animate-spin text-[var(--evergreen)]" />
        ) : (
          <GitBranch className="mx-auto mb-3 text-[var(--paper-faint)]" />
        )}
        <p className="text-sm font-medium text-[var(--paper)]">
          {pending ? "Executing bounded graph" : "Trace not started"}
        </p>
        <p className="mt-1 text-xs text-[var(--paper-dim)]">
          {pending
            ? "Every transition will be shown here."
            : "Start an investigation to inspect each node."}
        </p>
      </div>
    </div>
  );
}

function TraceRow({ step }: { step: AgentTraceStep }) {
  const rejected = step.message.includes("REJECTED") || step.status === "REJECTED";
  const unresolved = step.status === "UNRESOLVED";
  return (
    <li className={`flex gap-3 rounded-xl border p-3 ${rejected || unresolved ? "border-[rgba(226,96,79,0.35)] bg-[var(--ink-700)]" : "border-[var(--line)] bg-[var(--ink-700)]"}`}>
      <span
        className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full ${
          rejected || unresolved
            ? "bg-[rgba(226,96,79,0.14)] text-[var(--crimson)]"
            : "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]"
        }`}
      >
        {rejected ? (
          <X size={12} />
        ) : unresolved ? (
          <TriangleAlert size={12} />
        ) : (
          <Check size={12} />
        )}
      </span>
      <div className="min-w-0">
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--paper-faint)]">
          {step.sequence}. {step.node.replaceAll("_", " ")}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{step.message}</p>
      </div>
    </li>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ShieldAlert;
  label: string;
  value: string;
}) {
  return (
    <div className="panel rounded-xl p-4">
      <Icon size={15} className="mb-4 text-[var(--evergreen)]" />
      <p className="number-tabular font-mono text-lg font-semibold tracking-[-0.025em] text-[var(--paper)]">{value}</p>
      <p className="mt-1 text-[11px] text-[var(--paper-dim)]">{label}</p>
    </div>
  );
}
