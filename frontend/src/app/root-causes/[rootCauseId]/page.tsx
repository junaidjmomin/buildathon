"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Check,
  GitBranch,
  RefreshCw,
  SearchCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  InlineNotice,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { AgentTraceStep, InvestigationExecution } from "@/types/api";

export default function RootCausePage() {
  const { rootCauseId } = useParams<{ rootCauseId: string }>();
  const root = useQuery({
    queryKey: ["root-cause", rootCauseId],
    queryFn: () => api.rootCause(rootCauseId),
  });
  const investigation = useMutation({ mutationFn: () => api.investigateRootCause(rootCauseId) });

  if (root.isPending) {
    return <WorkspaceLoading label="Loading root cause evidence" />;
  }
  if (root.isError || !root.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Root cause" onRetry={() => root.refetch()} />
      </main>
    );
  }

  const data = root.data;
  const execution = investigation.data;

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: "/root-causes", label: "Root causes" }}
          eyebrow={
            <>
              <GitBranch size={14} /> Root-cause evidence
            </>
          }
          title={data.title}
          subtitle={
            <>
              {data.category.replaceAll("_", " ")} · <span className="font-mono">{data.id}</span>
            </>
          }
        />
        <Badge
          label={data.verification_status.replaceAll("_", " ")}
          status={
            data.verification_status === "PROVEN"
              ? "PASS"
              : data.verification_status === "REJECTED"
                ? "VIOLATION"
                : "UNRESOLVED"
          }
        />
      </div>

      <SummaryStrip
        className="mb-6"
        columns="five"
        label="Root cause impact summary"
        items={[
          { label: "Verified impact", value: formatMoney(data.verified_impact), tone: "negative" },
          { label: "Affected payments", value: data.affected_count.toLocaleString("en-IN") },
          { label: "Primary violations", value: data.primary_violation_count.toLocaleString("en-IN") },
          { label: "Downstream effects", value: data.downstream_effect_count.toLocaleString("en-IN") },
          { label: "Expected → observed", value: `${data.expected_value} → ${data.observed_value}` },
        ]}
      />

      <section className="panel mb-6 overflow-hidden rounded-xl">
        <SectionHeader
          title="Investigation workflow"
          description="Collect evidence, form bounded hypotheses, and submit each conclusion to deterministic verification. The workflow cannot modify controls or financial truth."
          meta={execution ? <Badge label={execution.status} status={execution.status === "PROVEN" ? "PASS" : "UNRESOLVED"} /> : null}
        />
        <div className="flex flex-col justify-between gap-4 px-5 py-4 sm:flex-row sm:items-center">
          <div className="min-w-0 text-xs text-[var(--paper-dim)]">
            {execution ? (
              <p>
                Last execution <span className="font-mono text-[var(--paper)]">{execution.execution_id}</span> ·{" "}
                {execution.completed_at}
              </p>
            ) : (
              <p>No investigation execution has been started in this session.</p>
            )}
          </div>
          <button
            aria-busy={investigation.isPending}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-xs font-semibold text-[var(--ink-800)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
            disabled={investigation.isPending}
            onClick={() => investigation.mutate()}
            type="button"
          >
            {execution ? <RefreshCw aria-hidden="true" size={14} /> : <SearchCheck aria-hidden="true" size={14} />}
            {investigation.isPending ? "Investigating…" : execution ? "Run fresh investigation" : "Start investigation"}
          </button>
        </div>
      </section>

      {investigation.error ? (
        <InlineNotice className="mb-6" tone="negative">
          {investigation.error instanceof ApiError
            ? investigation.error.message
            : "The investigation could not be started."}
        </InlineNotice>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
        <section className="panel overflow-hidden rounded-xl">
          <SectionHeader
            title="Execution trace"
            description="Ordered transitions, retries, and evidence boundaries from the investigation run."
            meta={execution ? `${execution.trace.length.toLocaleString("en-IN")} steps` : null}
          />
          {investigation.isPending && !execution ? (
            <div aria-live="polite" className="grid min-h-64 place-items-center px-5 text-center" role="status">
              <div>
                <RefreshCw className="mx-auto animate-spin text-[var(--evergreen)]" size={20} />
                <p className="mt-3 text-sm font-medium text-[var(--paper)]">Executing bounded workflow</p>
                <p className="mt-1 text-xs text-[var(--paper-dim)]">The ordered trace will appear here.</p>
              </div>
            </div>
          ) : execution?.trace.length ? (
            <ol aria-label="Investigation execution trace" className="divide-y divide-[var(--line)]">
              {execution.trace.map((step, index) => (
                <TraceRow key={`${step.sequence}-${step.node}-${index}`} step={step} />
              ))}
            </ol>
          ) : (
            <EmptySection
              body="Start an investigation to inspect every evidence and verification transition."
              title="Trace not started"
            />
          )}
        </section>

        <section className="panel self-start overflow-hidden rounded-xl">
          <SectionHeader
            title="Hypotheses and verified conclusion"
            description="Generated hypotheses stay visually separate from the deterministic verdict."
            meta={execution ? `${execution.attempt_count} attempt${execution.attempt_count === 1 ? "" : "s"}` : null}
          />
          {execution ? <InvestigationConclusion execution={execution} /> : (
            <EmptySection
              body="No conclusion is inferred before an investigation has produced and verified evidence."
              title="No investigation conclusion"
            />
          )}
        </section>
      </div>
    </main>
  );
}

function InvestigationConclusion({ execution }: { execution: InvestigationExecution }) {
  return (
    <div>
      <div className="border-b border-[var(--line)] px-5 py-3 text-[10px] text-[var(--paper-dim)]">
        <span className="font-semibold text-[var(--paper)]">Runtime:</span>{" "}
        {execution.llm_used
          ? `${execution.llm_provider ?? "Configured provider"} · ${execution.llm_model ?? "configured model"}`
          : "Deterministic fallback"}
      </div>
      {execution.hypotheses.length ? (
        <div className="divide-y divide-[var(--line)]">
          {execution.hypotheses.map((hypothesis, index) => (
            <article className="px-5 py-4" key={hypothesis.hypothesis_id}>
              <p className="text-[9px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
                Hypothesis {index + 1} · {hypothesis.kind.replaceAll("_", " ")}
              </p>
              <p className="mt-2 text-sm font-medium leading-5 text-[var(--paper)]">{hypothesis.statement}</p>
              <p className="mt-2 text-xs leading-5 text-[var(--paper-dim)]">{hypothesis.rationale}</p>
              <p className="mt-2 font-mono text-[9px] text-[var(--paper-faint)]">
                {hypothesis.evidence_ids.length.toLocaleString("en-IN")} evidence references · confidence {hypothesis.confidence}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <p className="px-5 py-4 text-xs text-[var(--paper-dim)]">No hypotheses were returned.</p>
      )}
      {execution.verification ? (
        <div className="border-t-2 border-[var(--line-strong)] bg-[var(--ink-700)] px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--paper-faint)]">
                Deterministic verdict
              </p>
              <p
                className={`mt-1 text-lg font-semibold ${
                  execution.status === "PROVEN" ? "text-[var(--evergreen)]" : "text-[var(--amber)]"
                }`}
              >
                {execution.status}
              </p>
            </div>
            {execution.status === "PROVEN" ? (
              <Check aria-hidden="true" className="text-[var(--evergreen)]" size={20} />
            ) : (
              <TriangleAlert aria-hidden="true" className="text-[var(--amber)]" size={20} />
            )}
          </div>
          <p className="mt-3 text-xs font-semibold text-[var(--paper)]">
            {execution.verification.classification.replaceAll("_", " ")}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{execution.verification.conclusion}</p>
          {execution.case_id ? (
            <p className="mt-3 font-mono text-[10px] text-[var(--paper-faint)]">Evidence case {execution.case_id}</p>
          ) : null}
        </div>
      ) : (
        <InlineNotice className="m-5" tone="warning">No deterministic verification result was returned.</InlineNotice>
      )}
    </div>
  );
}

function TraceRow({ step }: { step: AgentTraceStep }) {
  const rejected = step.message.includes("REJECTED") || step.status === "REJECTED";
  const unresolved = step.status === "UNRESOLVED";
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)_auto] gap-3 px-5 py-4">
      <span
        className={`grid h-7 w-7 place-items-center rounded-full border ${
          rejected
            ? "border-[var(--crimson)] text-[var(--crimson)]"
            : unresolved
              ? "border-[var(--amber)] text-[var(--amber)]"
              : "border-[var(--evergreen)] text-[var(--evergreen)]"
        }`}
      >
        {rejected ? <X aria-hidden="true" size={12} /> : unresolved ? <TriangleAlert aria-hidden="true" size={12} /> : <Check aria-hidden="true" size={12} />}
      </span>
      <div className="min-w-0">
        <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
          {step.sequence}. {step.node.replaceAll("_", " ")}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">{step.message}</p>
      </div>
      <Badge
        label={step.status.replaceAll("_", " ")}
        status={rejected ? "VIOLATION" : unresolved ? "UNRESOLVED" : "PASS"}
      />
    </li>
  );
}
