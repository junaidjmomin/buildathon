"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileCheck2 } from "lucide-react";
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

export default function AgreementDetailPage() {
  const { agreementId } = useParams<{ agreementId: string }>();
  const agreement = useQuery({
    queryKey: ["agreement", agreementId],
    queryFn: () => api.agreement(agreementId),
  });
  const proposals = useQuery({
    queryKey: ["agreement-proposals", agreementId],
    queryFn: () => api.agreementProposals(agreementId),
  });

  if (agreement.isPending) {
    return <WorkspaceLoading label="Loading agreement provenance" />;
  }

  if (agreement.isError || !agreement.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="The agreement" onRetry={() => agreement.refetch()} />
      </main>
    );
  }

  const record = agreement.data;
  const approvedControls = (proposals.data ?? [])
    .filter((proposal) => proposal.status === "APPROVED")
    .sort((a, b) =>
      a.proposed_control.logical_control_key.localeCompare(b.proposed_control.logical_control_key),
    );

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: "/agreements", label: "Agreements" }}
          eyebrow={
            <>
              <FileCheck2 size={14} /> Agreement provenance
            </>
          }
          title={record.title}
          subtitle={
            <>
              {record.merchant} · {record.effective_from} → {record.effective_to ?? "open"}
            </>
          }
        />
        <Badge
          label={record.status.replaceAll("_", " ")}
          status={record.status === "APPROVED" ? "PASS" : "INFO"}
        />
      </div>

      <SummaryStrip
        className="mb-6"
        label="Agreement record summary"
        items={[
          { label: "Source", value: record.source_type.replaceAll("_", " ") },
          { label: "Clauses indexed", value: record.clauses.length.toLocaleString("en-IN") },
          { label: "Agreement ID", value: record.id },
          { label: "Content fingerprint", value: record.content_hash, detail: "Immutable source hash" },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
        <section className="panel overflow-hidden rounded-xl">
          <SectionHeader
            title="Source clauses"
            description="Exact text, page provenance, and effective window for each indexed clause."
            meta={`${record.clauses.length.toLocaleString("en-IN")} clauses`}
          />
          {record.clauses.length ? (
            <ol className="divide-y divide-[var(--line)]">
              {record.clauses.map((clause) => (
                <li className="px-5 py-4" key={clause.id}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[var(--evergreen)]">
                        Clause {clause.clause_number ?? clause.reference}
                      </p>
                      <h3 className="mt-1 text-xs font-semibold text-[var(--paper)]">
                        {clause.clause_title ?? clause.heading}
                      </h3>
                    </div>
                    <div className="text-right font-mono text-[9px] text-[var(--paper-faint)]">
                      <p>{clause.source_type === "MANUAL_ENTRY" ? "Manual entry" : `Page ${clause.page}`}</p>
                      <p className="mt-1">
                        {clause.effective_from} → {clause.effective_to ?? "open"}
                      </p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-[var(--paper-dim)]">{clause.text}</p>
                  <p className="mt-2 truncate font-mono text-[9px] text-[var(--paper-faint)]">{clause.id}</p>
                </li>
              ))}
            </ol>
          ) : (
            <EmptySection
              body="No source clauses have been indexed for this agreement."
              title="No clauses available"
            />
          )}
        </section>

        <section className="panel self-start overflow-hidden rounded-xl">
          <SectionHeader
            title="Approved controls"
            description="Activated definitions derived from this agreement and linked back to their source clause."
            meta={proposals.isPending ? "Loading…" : `${approvedControls.length.toLocaleString("en-IN")} approved`}
          />
          {proposals.isPending ? (
            <div aria-busy="true" className="space-y-3 p-5" role="status">
              <span className="sr-only">Loading approved controls</span>
              <div className="skeleton h-16" />
              <div className="skeleton h-16" />
              <div className="skeleton h-16" />
            </div>
          ) : proposals.isError ? (
            <div className="p-5">
              <ErrorState what="Control proposals" onRetry={() => proposals.refetch()} />
            </div>
          ) : approvedControls.length ? (
            <div className="divide-y divide-[var(--line)]">
              {approvedControls.map((proposal) => {
                const control = proposal.proposed_control;
                const clause = record.clauses.find((item) => item.id === proposal.clause_id);
                return (
                  <Link
                    className="group flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-[var(--ink-600)]"
                    href={`/controls/${control.logical_control_key}`}
                    key={proposal.id}
                  >
                    <div className="min-w-0">
                      <p className="truncate font-mono text-[9px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
                        {control.logical_control_key} · v{control.version}
                      </p>
                      <h3 className="mt-1 truncate text-xs font-semibold text-[var(--paper)]">{control.name}</h3>
                      <p className="mt-1 truncate text-[11px] text-[var(--paper-dim)]">
                        Clause {clause?.clause_number ?? clause?.reference ?? proposal.clause_id}
                      </p>
                    </div>
                    <ArrowRight
                      aria-hidden="true"
                      className="shrink-0 text-[var(--paper-faint)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--evergreen)]"
                      size={14}
                    />
                  </Link>
                );
              })}
            </div>
          ) : (
            <EmptySection
              body="Extract, verify, and approve proposals in the Agreements workspace before they appear here."
              title="No approved controls"
              action={
                <Link className="font-semibold text-[var(--evergreen)] underline underline-offset-2" href="/agreements">
                  Open agreement workspace
                </Link>
              }
            />
          )}
        </section>
      </div>
    </main>
  );
}
