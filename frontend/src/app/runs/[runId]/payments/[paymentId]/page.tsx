"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, Banknote, Check, CircleAlert, FileText, GitBranch, Scale } from "lucide-react";
import { useParams } from "next/navigation";

import { Badge, ErrorState, MoneyText, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { api } from "@/lib/api";
import { compareDecimals, formatMoney } from "@/lib/format";
import type { EvaluationStatus } from "@/types/api";

const cashKeys = ["gross", "mdr", "gst", "refunds", "other_fees", "net"] as const;

export default function PaymentPage() {
  const params = useParams<{ runId: string; paymentId: string }>();
  const payment = useQuery({
    queryKey: ["payment", params.runId, params.paymentId],
    queryFn: () => api.expectedActual(params.runId, params.paymentId),
  });
  const graph = useQuery({
    queryKey: ["payment-graph", params.runId, params.paymentId],
    queryFn: () => api.paymentGraph(params.runId, params.paymentId),
  });
  const lineage = useQuery({
    queryKey: ["lineage", params.runId, params.paymentId],
    queryFn: () => api.lineage(params.runId, params.paymentId),
  });
  const counterfactual = useQuery({
    queryKey: ["counterfactual", params.runId, params.paymentId],
    queryFn: () => api.counterfactual(params.runId, params.paymentId),
  });

  if (payment.isPending) {
    return <WorkspaceLoading label="Loading payment proof" />;
  }
  if (payment.isError || !payment.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Payment evidence" onRetry={() => payment.refetch()} />
      </main>
    );
  }

  const data = payment.data;
  const isUnresolved = data.status === "UNRESOLVED";
  const traditionalMatch =
    data.bank_credit !== null && compareDecimals(data.gateway_net, data.bank_credit) === 0;
  const hasLeakage = compareDecimals(data.verified_leakage, "0") > 0;

  return (
    <main className="mx-auto max-w-[1240px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: "/", label: "Control run" }}
          eyebrow={
            <>
              <FileText size={14} /> Payment proof
            </>
          }
          title={data.payment_id}
          subtitle={
            <>
              {data.descriptor} · Run <span className="font-mono text-[var(--paper)]">{params.runId}</span>
            </>
          }
        />
        <Badge
          label={data.status === "VIOLATION" ? "Control violation" : data.status}
          status={statusTone(data.status)}
        />
      </div>

      <SummaryStrip
        className="mb-6"
        label="Payment evidence summary"
        items={[
          { label: "Payment amount", value: formatMoney(data.amount) },
          { label: "Expected net", value: formatMoney(data.expected_net) },
          { label: "Gateway net", value: formatMoney(data.gateway_net) },
          {
            label: "Verified leakage",
            value: formatMoney(data.verified_leakage),
            detail: isUnresolved ? "Evidence boundary preserved" : `${data.evidence.length} evidence records`,
            tone: hasLeakage ? "negative" : isUnresolved ? "warning" : "positive",
          },
        ]}
      />

      <section aria-label="Reconciliation comparison" className="mb-6 grid gap-4 md:grid-cols-2">
        <Comparison
          icon={Banknote}
          label="Traditional reconciliation"
          pass={traditionalMatch}
          result={traditionalMatch ? "MATCH" : data.bank_credit === null ? "UNRESOLVED" : "MISMATCH"}
          rows={[
            ["Gateway net", formatMoney(data.gateway_net)],
            ["Bank credit", formatMoney(data.bank_credit)],
          ]}
        />
        <Comparison
          icon={Scale}
          label="Control verification"
          pass={data.status === "PASS"}
          result={data.status}
          rows={[
            ["Expected net", formatMoney(data.expected_net)],
            ["Actual net", formatMoney(data.gateway_net)],
          ]}
        />
      </section>

      <section className="panel mb-6 overflow-hidden rounded-xl">
        <SectionHeader
          title="Expected versus actual"
          description="Expected state is calculated independently from the observed settlement record."
          meta={
            <span className="font-mono text-[10px]">
              {data.applied_control_id} · v{data.applied_control_version} · {data.applied_control_effective_period}
            </span>
          }
        />
        {data.rows.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left">
              <caption className="sr-only">Expected and actual payment cash components</caption>
              <thead className="bg-[var(--ink-600)] text-[10px] uppercase tracking-[0.11em] text-[var(--paper-faint)]">
                <tr>
                  <th className="px-5 py-3" scope="col">Cash component</th>
                  <th className="px-4 py-3 text-right" scope="col">Expected</th>
                  <th className="px-4 py-3 text-right" scope="col">Actual</th>
                  <th className="px-5 py-3 text-right" scope="col">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {data.rows.map((row) => (
                  <tr key={row.label}>
                    <th className="px-5 py-3.5 text-sm font-medium text-[var(--paper)]" scope="row">{row.label}</th>
                    <td className="number-tabular px-4 py-3.5 text-right font-mono text-sm text-[var(--paper-dim)]">
                      {formatMoney(row.expected)}
                    </td>
                    <td
                      className={`number-tabular px-4 py-3.5 text-right font-mono text-sm ${
                        row.status === "VIOLATION" ? "font-semibold text-[var(--crimson)]" : "text-[var(--paper)]"
                      }`}
                    >
                      {formatMoney(row.actual)}
                    </td>
                    <td className="px-5 py-3.5 text-right"><StatusBadge status={row.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptySection body="No expected-versus-actual rows were returned." title="No component evidence" />
        )}
      </section>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <CounterfactualPanel query={counterfactual} />
        <LineagePanel query={lineage} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
        <section className="panel overflow-hidden rounded-xl">
          <SectionHeader
            title="Control evidence"
            description="Calculation, source clause, and immutable evaluation references for each check."
            meta={`${data.evidence.length.toLocaleString("en-IN")} records`}
          />
          {data.evidence.length ? (
            <div className="divide-y divide-[var(--line)]">
              {data.evidence.map((evidence, index) => {
                const failed = evidence.difference !== null && compareDecimals(evidence.difference, "0") > 0;
                return (
                  <article className="px-5 py-4" key={`${evidence.control}-${index}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-xs font-semibold text-[var(--paper)]">{evidence.title}</h3>
                        <p className="mt-1 font-mono text-[9px] text-[var(--paper-faint)]">{evidence.control}</p>
                      </div>
                      {failed ? (
                        <CircleAlert aria-hidden="true" className="shrink-0 text-[var(--crimson)]" size={15} />
                      ) : (
                        <Check aria-hidden="true" className="shrink-0 text-[var(--evergreen)]" size={15} />
                      )}
                    </div>
                    <p className="number-tabular mt-3 overflow-x-auto rounded-lg bg-[var(--ink-700)] px-3 py-2.5 font-mono text-xs text-[var(--paper-dim)]">
                      {evidence.calculation}
                    </p>
                    <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
                      <EvidenceValue label="Expected" value={formatMoney(evidence.expected)} />
                      <EvidenceValue label="Actual" value={formatMoney(evidence.actual)} />
                      <EvidenceValue label="Difference" value={formatMoney(evidence.difference)} tone={failed ? "negative" : "default"} />
                    </dl>
                    <div className="mt-3 border-t border-[var(--line)] pt-3 text-[10px] leading-4 text-[var(--paper-dim)]">
                      <p>{evidence.source} · <span className="font-medium text-[var(--evergreen)]">{evidence.source_clause}</span></p>
                      <p className="mt-1 font-mono text-[9px] text-[var(--paper-faint)]">
                        {[
                          evidence.control_version ? `control v${evidence.control_version}` : null,
                          evidence.evaluation_id ? `evaluation ${evidence.evaluation_id}` : null,
                          evidence.source_snapshot_ids?.length
                            ? `${evidence.source_snapshot_ids.length} source snapshot${evidence.source_snapshot_ids.length === 1 ? "" : "s"}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptySection body="No control evidence records were returned for this payment." title="No evidence records" />
          )}
        </section>

        <MoneyTracePanel query={graph} />
      </div>
    </main>
  );
}

function Comparison({
  label,
  icon: Icon,
  rows,
  result,
  pass,
}: {
  label: string;
  icon: typeof Banknote;
  rows: [string, string][];
  result: string;
  pass: boolean;
}) {
  const unresolved = result === "UNRESOLVED";
  return (
    <article className="panel overflow-hidden rounded-xl">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3.5">
        <h2 className="flex items-center gap-2 text-xs font-semibold text-[var(--paper)]">
          <Icon aria-hidden="true" className="text-[var(--paper-faint)]" size={14} /> {label}
        </h2>
        <Badge label={result} status={pass ? "PASS" : unresolved ? "UNRESOLVED" : "VIOLATION"} />
      </div>
      <dl className="divide-y divide-[var(--line)]">
        {rows.map(([name, value]) => (
          <div className="flex justify-between gap-4 px-5 py-3 text-sm" key={name}>
            <dt className="text-[var(--paper-dim)]">{name}</dt>
            <dd className="number-tabular font-mono font-semibold text-[var(--paper)]">{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function CounterfactualPanel({ query }: { query: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.counterfactual>>, Error>> }) {
  return (
    <section className="panel overflow-hidden rounded-xl">
      <SectionHeader
        title="Counterfactual settlement"
        description="Observed cash flow compared with the verified correct cash flow."
      />
      {query.isPending ? (
        <div aria-busy="true" className="space-y-3 p-5" role="status"><span className="sr-only">Loading counterfactual settlement</span><div className="skeleton h-32" /><div className="skeleton h-12" /></div>
      ) : query.isError || !query.data ? (
        <div className="p-5"><ErrorState what="Counterfactual settlement" onRetry={() => query.refetch()} /></div>
      ) : (
        <div className="p-5">
          <div className="grid grid-cols-[1fr_auto_auto] gap-x-5 gap-y-3 text-xs">
            <span />
            <strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Actual</strong>
            <strong className="text-right text-[10px] uppercase tracking-[0.1em] text-[var(--evergreen)]">Correct</strong>
            {cashKeys.map((key) => (
              <div className="contents" key={key}>
                <span className={`capitalize text-[var(--paper-dim)] ${key === "net" ? "border-t border-[var(--line-strong)] pt-3 font-semibold text-[var(--paper)]" : ""}`}>
                  {key.replaceAll("_", " ")}
                </span>
                <span className={`number-tabular text-right font-mono text-[var(--paper-dim)] ${key === "net" ? "border-t border-[var(--line-strong)] pt-3 font-semibold text-[var(--paper)]" : ""}`}>
                  {formatMoney(query.data.actual[key])}
                </span>
                <span className={`number-tabular text-right font-mono text-[var(--paper-dim)] ${key === "net" ? "border-t border-[var(--line-strong)] pt-3 font-semibold text-[var(--evergreen)]" : ""}`}>
                  {formatMoney(query.data.expected[key])}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-5 flex items-end justify-between gap-4 border-l-2 border-[var(--crimson)] bg-[var(--ink-700)] px-4 py-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">Correct settlement</p>
              <MoneyText amount={formatMoney(query.data.expected.net)} className="mt-1 text-lg" />
            </div>
            <div className="text-right">
              <p className="text-[10px] text-[var(--paper-faint)]">Difference</p>
              <MoneyText amount={formatMoney(query.data.difference)} className="mt-1 text-sm" tone="violation" />
            </div>
          </div>
          {query.data.drivers.length ? (
            <ul className="mt-3 space-y-1.5 text-[10px] text-[var(--paper-dim)]">
              {query.data.drivers.map((driver, index) => (
                <li className="flex justify-between gap-3" key={`${driver.type}-${index}`}>
                  <span>{driver.type.replaceAll("_", " ").toLowerCase()}</span>
                  <span className="number-tabular font-mono font-semibold text-[var(--paper)]">{formatMoney(driver.amount)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </section>
  );
}

function LineagePanel({ query }: { query: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.lineage>>, Error>> }) {
  return (
    <section className="panel overflow-hidden rounded-xl">
      <SectionHeader
        title="Violation lineage"
        description="Primary failures and their downstream effects, without double-counting causes."
        meta={query.data ? `${query.data.primary_violation_count} primary · ${query.data.downstream_effect_count} downstream` : null}
      />
      {query.isPending ? (
        <div aria-busy="true" className="space-y-3 p-5" role="status"><span className="sr-only">Loading violation lineage</span><div className="skeleton h-20" /><div className="skeleton h-20" /></div>
      ) : query.isError || !query.data ? (
        <div className="p-5"><ErrorState what="Violation lineage" onRetry={() => query.refetch()} /></div>
      ) : query.data.nodes.length ? (
        <div className="p-5">
          {query.data.nodes.map((node, index) => (
            <div key={node.id}>
              <article className={`border-l-2 bg-[var(--ink-700)] px-4 py-3 ${node.lineage_type === "PRIMARY" ? "border-[var(--crimson)]" : "border-[var(--line-strong)]"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className={`text-[9px] font-semibold uppercase tracking-[0.11em] ${node.lineage_type === "PRIMARY" ? "text-[var(--crimson)]" : "text-[var(--paper-faint)]"}`}>
                      {node.lineage_type}
                    </p>
                    <p className="mt-1 text-xs font-semibold text-[var(--paper)]">{node.category.replaceAll("_", " ")}</p>
                  </div>
                  <span className="number-tabular font-mono text-xs font-semibold text-[var(--paper)]">{formatMoney(node.difference)}</span>
                </div>
                <p className="mt-2 text-[10px] leading-4 text-[var(--paper-dim)]">
                  {typeof node.causal_evidence === "string" ? node.causal_evidence : JSON.stringify(node.causal_evidence)}
                </p>
              </article>
              {index < query.data.nodes.length - 1 ? <ArrowDown aria-hidden="true" className="mx-auto my-1 text-[var(--paper-faint)]" size={13} /> : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptySection body="No primary or downstream violations were linked to this payment." title="No violation lineage" />
      )}
    </section>
  );
}

function MoneyTracePanel({ query }: { query: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.paymentGraph>>, Error>> }) {
  return (
    <section className="panel self-start overflow-hidden rounded-xl">
      <SectionHeader title="Money trace" description="Matched lifecycle nodes in settlement order." meta={<GitBranch aria-hidden="true" size={14} />} />
      {query.isPending ? (
        <div aria-busy="true" className="space-y-3 p-5" role="status"><span className="sr-only">Loading money trace</span><div className="skeleton h-16" /><div className="skeleton h-16" /><div className="skeleton h-16" /></div>
      ) : query.isError || !query.data ? (
        <div className="p-5"><ErrorState what="Money trace" onRetry={() => query.refetch()} /></div>
      ) : query.data.nodes.length ? (
        <div className="p-5">
          {query.data.nodes.map((node, index) => (
            <div key={`${node.id}-${index}`}>
              <article className={`border-l-2 bg-[var(--ink-700)] px-4 py-3 ${node.status === "VIOLATION" ? "border-[var(--crimson)]" : "border-[var(--evergreen)]"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">{node.kind.replaceAll("_", " ")}</p>
                    <p className="mt-1 truncate text-xs font-semibold text-[var(--paper)]">{node.label}</p>
                    <p className="mt-1 truncate font-mono text-[9px] text-[var(--paper-faint)]">{node.id}</p>
                  </div>
                  <div className="text-right">
                    <p className="number-tabular font-mono text-xs font-semibold text-[var(--paper)]">{formatMoney(node.amount)}</p>
                    {node.detail ? <p className={`mt-1 text-[9px] ${node.status === "VIOLATION" ? "text-[var(--crimson)]" : "text-[var(--paper-dim)]"}`}>{node.detail}</p> : null}
                  </div>
                </div>
              </article>
              {index < query.data.nodes.length - 1 ? <div className="ml-4 h-3 border-l border-dashed border-[var(--line-strong)]" /> : null}
            </div>
          ))}
          <p className="mt-4 border-t border-[var(--line)] pt-3 text-[10px] leading-4 text-[var(--paper-dim)]">
            Relationships use exact identifiers or typed matching rules; ambiguous links remain unresolved.
          </p>
        </div>
      ) : (
        <EmptySection body="No lifecycle nodes were matched for this payment." title="No money trace" />
      )}
    </section>
  );
}

function EvidenceValue({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "negative" }) {
  return (
    <div>
      <dt className="text-[10px] text-[var(--paper-faint)]">{label}</dt>
      <dd className={`number-tabular mt-1 font-mono font-semibold ${tone === "negative" ? "text-[var(--crimson)]" : "text-[var(--paper)]"}`}>
        {value}
      </dd>
    </div>
  );
}

function statusTone(status: EvaluationStatus): "PASS" | "VIOLATION" | "UNRESOLVED" | "PENDING" {
  if (status === "PASS") return "PASS";
  if (status === "UNRESOLVED") return "UNRESOLVED";
  if (status === "WARNING") return "PENDING";
  return "VIOLATION";
}

function StatusBadge({ status }: { status: EvaluationStatus }) {
  return <Badge label={status} status={statusTone(status)} />;
}
