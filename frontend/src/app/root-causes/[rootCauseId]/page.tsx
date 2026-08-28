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

import { AppShell } from "@/components/app-shell";
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
      <AppShell>
        <div className="grid min-h-[calc(100vh-64px)] place-items-center">
          <LoaderCircle
            aria-label="Loading root cause"
            className="animate-spin text-[#1e6b51]"
          />
        </div>
      </AppShell>
    );
  }
  if (!root.data) {
    return (
      <AppShell>
        <main className="p-8" role="alert">
          Root cause could not be loaded.
        </main>
      </AppShell>
    );
  }
  const data = root.data;
  const execution = investigation.data;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-[#5e6a64]"
        >
          <ArrowLeft size={14} /> Back to control run
        </Link>

        <section className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">
              <GitBranch size={14} /> Systemic root cause
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">{data.title}</h1>
            <p className="mt-2 text-sm text-[#66716b]">
              {data.category} · {data.id}
            </p>
          </div>
          <div className="rounded-xl border border-[#efc6b3] bg-[#fff5ef] px-5 py-3 text-right">
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#b95a35]">
              Verified impact
            </p>
            <p className="mt-1 text-2xl font-semibold text-[#a9431f]">
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

        <section className="mb-5 rounded-2xl border border-[#cfded4] bg-[#edf7f0] p-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <BrainCircuit size={17} className="text-[#1e6b51]" />
                {execution?.orchestration_used ? `${execution.orchestration_provider} orchestration` : "Deterministic investigation"}
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-[#5f6e65]">
                Orchestrates evidence collection, structured hypotheses, deterministic
                verification, bounded retries, and human workflow. It cannot change financial
                truth or controls.
              </p>
            </div>
            <button
              type="button"
              onClick={() => investigation.mutate()}
              disabled={investigation.isPending}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[#112a2b] px-4 py-2.5 text-xs font-semibold text-white disabled:cursor-wait disabled:opacity-60"
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
            <p className="mt-4 text-xs text-[#a9431f]" role="alert">
              {investigation.error instanceof ApiError
                ? investigation.error.message
                : "The investigation could not be started."}
            </p>
          ) : null}
        </section>

        <section className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[#e2e5df] px-5 py-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <GitBranch size={16} className="text-[#1e6b51]" /> Execution trace
              </h2>
              <p className="mt-1 text-xs text-[#78827d]">
                Explicit nodes, branches, retries, and authority boundaries
              </p>
            </div>
            <div className="p-5">
              {!execution ? (
                <EmptyTrace pending={investigation.isPending} />
              ) : (
                <ol className="space-y-3" aria-label="Agent execution trace">
                  {execution.trace.map((step) => (
                    <TraceRow key={`${step.sequence}-${step.node}`} step={step} />
                  ))}
                </ol>
              )}
            </div>
          </div>

          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[#e2e5df] px-5 py-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Scale size={16} className="text-[#1e6b51]" /> Hypotheses and verdict
              </h2>
              <p className="mt-1 text-xs text-[#78827d]">
                Model proposals remain subordinate to deterministic verification
              </p>
            </div>
            <div className="p-5">
              {!execution ? (
                <div className="grid min-h-64 place-items-center text-center">
                  <div>
                    <Scale className="mx-auto mb-3 text-[#a6afa9]" />
                    <p className="text-sm font-medium">No agent conclusion</p>
                    <p className="mt-1 text-xs text-[#78827d]">Nothing is inferred in advance.</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2 text-[10px]">
                    <span className="rounded-full bg-[#e8f2eb] px-2.5 py-1 font-semibold text-[#1e6b51]">
                      {execution.llm_used
                        ? `${execution.llm_provider ?? "LLM"} · ${execution.llm_model ?? "configured model"}`
                        : "Deterministic fallback"}
                    </span>
                    <span className="text-[#78827d]">
                      {execution.attempt_count} attempt
                      {execution.attempt_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {execution.hypotheses.map((hypothesis, index) => (
                    <article
                      key={hypothesis.hypothesis_id}
                      className="rounded-xl border border-[#dfe5df] bg-[#f8faf7] p-4"
                    >
                      <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#6b7770]">
                        Attempt {index + 1} · {hypothesis.kind.replaceAll("_", " ")}
                      </p>
                      <p className="mt-2 text-sm font-medium leading-6">
                        “{hypothesis.statement}”
                      </p>
                      <p className="mt-2 text-[10px] leading-5 text-[#6c7771]">
                        {hypothesis.rationale}
                      </p>
                    </article>
                  ))}
                  {execution.verification ? (
                    <div
                      className={`rounded-xl border p-4 ${
                        execution.status === "PROVEN"
                          ? "border-[#b8dbc7] bg-[#eff9f2]"
                          : "border-[#efc6b3] bg-[#fff8f4]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#607069]">
                            Deterministic final result
                          </p>
                          <p className="mt-1 text-xl font-semibold">{execution.status}</p>
                        </div>
                        {execution.status === "PROVEN" ? (
                          <Check size={22} className="text-[#1e6b51]" />
                        ) : (
                          <TriangleAlert size={22} className="text-[#b95a35]" />
                        )}
                      </div>
                      <p className="mt-3 text-xs font-semibold">
                        {execution.verification.classification.replaceAll("_", " ")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[#5f6e65]">
                        {execution.verification.conclusion}
                      </p>
                      {execution.case_id ? (
                        <p className="mt-3 text-[10px] font-semibold text-[#1e6b51]">
                          Evidence case: {execution.case_id}
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
    </AppShell>
  );
}

function EmptyTrace({ pending }: { pending: boolean }) {
  return (
    <div className="grid min-h-64 place-items-center text-center" aria-live="polite">
      <div>
        {pending ? (
          <LoaderCircle className="mx-auto mb-3 animate-spin text-[#1e6b51]" />
        ) : (
          <GitBranch className="mx-auto mb-3 text-[#a6afa9]" />
        )}
        <p className="text-sm font-medium">
          {pending ? "Executing bounded graph" : "Trace not started"}
        </p>
        <p className="mt-1 text-xs text-[#78827d]">
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
    <li className="flex gap-3 rounded-xl border border-[#e1e5df] bg-white p-3">
      <span
        className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full ${
          rejected || unresolved
            ? "bg-[#fff0e8] text-[#b95a35]"
            : "bg-[#e8f2eb] text-[#1e6b51]"
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
        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#6d7772]">
          {step.sequence}. {step.node.replaceAll("_", " ")}
        </p>
        <p className="mt-1 text-xs leading-5 text-[#47534d]">{step.message}</p>
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
      <Icon size={15} className="mb-4 text-[#1e6b51]" />
      <p className="number-tabular text-lg font-semibold tracking-[-0.025em]">{value}</p>
      <p className="mt-1 text-[11px] text-[#727d77]">{label}</p>
    </div>
  );
}
